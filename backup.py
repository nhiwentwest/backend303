#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import numpy as np
from scipy import stats
from typing import List, Dict, Union, Tuple
import time
import json
import os
from dotenv import load_dotenv

# Cấu hình logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

class LosslessCompressor:
    BUFFER_OVERWRITE_MARKER = 0xFF
    BLOCKSIZE_CHANGE_MARKER = 0xFE

    def __init__(self, config=None):
        """
        Khởi tạo LosslessCompressor
        
        Args:
            config: Dictionary chứa các tham số cấu hình
        """
        # Cấu hình mặc định
        self.config = {
            'block_size': 24,           # Kích thước block mặc định: 2 giờ (5 phút/giá trị)
            'min_block_size': 12,       # Kích thước block tối thiểu (1 giờ)
            'max_block_size': 48,       # Kích thước block tối đa (4 giờ)
            'similarity_threshold': 0.8,# Ngưỡng để xác định mẫu tương tự
            'num_buffers': 16,          # Số lượng buffer
            # Tham số cho multistage sampling
            'sampling_window': 5,       # Số giá trị block size thử nghiệm mỗi lần
            'sampling_trials': 2,       # Số vòng sampling
            'denial_window': 2,         # Không đổi block size nếu n mới nằm trong ±2 của n hiện tại
            'sampling_recent_size': 1000, # Số lượng giá trị gần nhất để sampling
            'sampling_interval': 10     # Số block giữa 2 lần sampling, mặc định 10 cho dữ liệu nhỏ
        }
        
        if config:
            self.config.update(config)
        
        self.block_size = self.config['block_size']
        self.buffers = []
        self.encoded_stream = []
        
        # Thêm các biến mới cho việc theo dõi và tạo biểu đồ
        self.block_size_history = []  # Lịch sử thay đổi kích thước block
        self.continuous_hit_ratio = []  # Tỷ lệ hit liên tục
        self.hit_ratio_by_block = []  # Tỷ lệ hit theo block
        self.window_hit_count = 0  # Số hit trong cửa sổ hiện tại
        self.window_blocks = 0  # Số block trong cửa sổ hiện tại
        self.similarity_scores = []  # Lịch sử điểm tương đồng
        self.cer_values = []  # Lịch sử giá trị CER
        
        # Thêm các biến theo dõi ổn định
        self.stability_score = 20  # Điểm ổn định ban đầu
        self.max_stability_score = 100  # Điểm ổn định tối đa
        self.stable_periods = 0  # Số chu kỳ ổn định
        self.stability_threshold = 5  # Ngưỡng để xác định ổn định
        self.in_stabilization_phase = False  # Đang trong giai đoạn ổn định?
        self.stability_hit_ratios = []  # Lịch sử hit ratio trong giai đoạn ổn định
        self.stability_window_size = 10  # Kích thước cửa sổ ổn định
        self.stable_block_size = self.block_size  # Kích thước block ổn định hiện tại
        self.last_adjustment_block = 0  # Block cuối cùng được điều chỉnh
        self.min_adjustment_interval = 5  # Khoảng cách tối thiểu giữa các lần điều chỉnh
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        
        self.recent_data = []  # Lưu dữ liệu gần nhất để sampling block size
        
    def reset(self):
        """Reset compressor về trạng thái ban đầu"""
        self.block_size = self.config['block_size']
        self.buffers = []
        self.encoded_stream = []
        
        # Reset các biến theo dõi
        self.block_size_history = []
        self.continuous_hit_ratio = []
        self.hit_ratio_by_block = []
        self.window_hit_count = 0
        self.window_blocks = 0
        self.similarity_scores = []
        self.cer_values = []
        
        
    def detect_trend(self, data: np.ndarray) -> str:
        """Phát hiện xu hướng trong dữ liệu: chỉ trả về 'up', 'down', 'stable'"""
        if len(data) < 2:
            return 'stable'
        slope = np.polyfit(np.arange(len(data)), data, 1)[0]
        if slope > 0.05:
            return 'up'
        elif slope < -0.05:
            return 'down'
        else:
            return 'stable'

    def calculate_cer(self, block1: np.ndarray, block2: np.ndarray) -> float:
        """
        Tính Compression Error Rate giữa hai block
        
        Args:
            block1: Block dữ liệu thứ nhất
            block2: Block dữ liệu thứ hai
            
        Returns:
            CER giữa hai block
        """
        if len(block1) != len(block2):
            return float('inf')
            
        differences = np.abs(block1 - block2)
        return np.mean(differences) / (np.max(block1) - np.min(block1))
        
    def calculate_correlation(self, data1: np.ndarray, data2: np.ndarray) -> float:
        """
        Tính hệ số tương quan Pearson giữa hai dãy dữ liệu
        
        Args:
            data1: Dãy dữ liệu thứ nhất
            data2: Dãy dữ liệu thứ hai
            
        Returns:
            Hệ số tương quan Pearson
        """
        if len(data1) != len(data2):
            return 0.0
            
        return np.corrcoef(data1, data2)[0, 1]
        
    def calculate_similarity_score(self, data1: np.ndarray, data2: np.ndarray) -> float:
        """
        Tính điểm tương đồng giữa hai dãy dữ liệu
        
        Args:
            data1: Dãy dữ liệu thứ nhất
            data2: Dãy dữ liệu thứ hai
            
        Returns:
            Điểm tương đồng tổng hợp
        """
        if len(data1) != len(data2):
            return 0.0
            
        # Tính KS test
        ks_stat, p_value = stats.ks_2samp(data1, data2)
        ks_score = 1.0 - ks_stat if p_value > 0.05 else 0.0  # Sử dụng p-value 0.05 làm ngưỡng
        
        # Tính correlation
        corr = self.calculate_correlation(data1, data2)
        
        # Tính CER
        cer = self.calculate_cer(data1, data2)
        cer_score = 1.0 - min(cer, 1.0)
        
        # Tính điểm tổng hợp với weights
        weights = {
            'ks_test': 0.3,    # KS test giúp đánh giá phân phối
            'correlation': 0.3, # Correlation đánh giá xu hướng
            'cer': 0.4         # CER đảm bảo độ chính xác
        }
        return (
            ks_score * weights['ks_test'] +
            corr * weights['correlation'] +
            cer_score * weights['cer']
        )
        
    def is_similar(self, data1: np.ndarray, data2: np.ndarray) -> bool:
        """
        Kiểm tra xem hai dãy dữ liệu có tương tự nhau không
        
        Args:
            data1: Dãy dữ liệu thứ nhất
            data2: Dãy dữ liệu thứ hai
            
        Returns:
            True nếu tương tự, False nếu không
        """
        if len(data1) != len(data2):
            return False
            
        # Kiểm tra KS test
        _, p_value = stats.ks_2samp(data1, data2)
        if p_value < 0.05:  # Ngưỡng p-value cho KS test
            return False
            
        # Kiểm tra correlation
        corr = self.calculate_correlation(data1, data2)
        if corr < 0.6:  # Ngưỡng correlation
            return False
            
        # Kiểm tra CER
        cer = self.calculate_cer(data1, data2)
        if cer > 0.1:  # Ngưỡng CER cho lossless compression
            return False
            
        return True
        
    def identify_pattern_type(self, data: np.ndarray) -> str:
        """Xác định loại mẫu dữ liệu, thêm log chi tiết"""
        if len(data) < 2:
            return 'unknown'
        mean = np.mean(data)
        std = np.std(data)
        diff = np.diff(data)
        sign_changes = np.sum(np.diff(np.sign(diff)) != 0)
        max_change = np.max(diff) / mean if mean != 0 else 0
        min_change = np.min(diff) / mean if mean != 0 else 0
        # Log chi tiết
        logging.info(f"[PATTERN_TYPE] mean={mean:.2f}, std={std:.2f}, max_change={max_change:.2f}, min_change={min_change:.2f}, sign_changes={sign_changes}")
        # Nếu số lần đổi dấu lớn (dao động nhiều), nhận là stable
        if sign_changes > len(data) // 4 and std/mean < 0.2:
            return 'stable'
        if max_change > self.config['pattern_types']['sudden_increase']['min_change']:
            return 'sudden_increase'
        elif min_change < self.config['pattern_types']['sudden_decrease']['min_change']:
            return 'sudden_decrease'
        elif std/mean < self.config['pattern_types']['stable']['max_variance']:
            return 'stable'
        elif self.is_periodic(data):
            return 'periodic'
        return 'unknown'

    def is_periodic(self, data: np.ndarray) -> bool:
        """Kiểm tra tính chu kỳ của dữ liệu"""
        if len(data) < self.config['pattern_types']['periodic']['period'] * 2:
            return False
            
        # Tính tự tương quan
        correlation = np.correlate(data, data, mode='full')
        correlation = correlation[len(correlation)//2:]
        
        # Tìm đỉnh trong tự tương quan
        peaks = np.where(np.diff(np.sign(np.diff(correlation))) < 0)[0] + 1
        if len(peaks) < 2:
            return False
            
        # Kiểm tra độ đều của chu kỳ
        periods = np.diff(peaks)
        return np.std(periods) / np.mean(periods) < 0.2

    def create_template(self, data: np.ndarray, pattern_type: str, timestamp, prev_blocks=None) -> int:
        """Tạo template mới với time_range là từ giờ đầu đến giờ cuối của chuỗi prev_blocks (liên tục cùng trend)."""
        if pattern_type not in self.templates['patterns']:
            self.templates['patterns'][pattern_type] = {}
            
        # Khởi tạo _template_id_counter nếu chưa có
        if '_template_id_counter' not in self.templates:
            self.templates['_template_id_counter'] = 0
            
        # Lấy và tăng template_id
        template_id = self.templates['_template_id_counter']
        self.templates['_template_id_counter'] += 1
        
        current_time = time.time()
        if prev_blocks and len(prev_blocks) > 0:
            hours = [ts.hour for ts in prev_blocks]
            hours = sorted(hours)
            time_range = {'start': min(hours), 'end': max(hours)}
            used_hours = hours.copy()
            hour = hours[-1]
        else:
            hour = timestamp.hour
            time_range = {'start': hour, 'end': hour}
            used_hours = [hour]
            
        date_str = timestamp.date().isoformat()
        trend = self.detect_trend(data)
        
        # Log chi tiết khi tạo template đầu tiên
        logger.info(f"[CREATE_TEMPLATE] id={template_id}, pattern_type={pattern_type}, time_range={time_range}, trend={trend}, used_hours={used_hours}, prev_blocks={prev_blocks}, timestamp={timestamp}")
        
        # Tạo template mới với ID đã lấy
        self.templates['patterns'][pattern_type][template_id] = {
            'data': data.copy(),
            'created_at': current_time,
            'last_used': current_time,
            'usage_count': 1,
            'occurrences': [],
            'variations': [],
            'importance': 0.0,
            'time_range': dict(time_range),
            'init_time_range': dict(time_range),
            'first_used_date': date_str,
            'last_used_date': date_str,
            'last_used_block': self.compression_stats['total_blocks'],
            'trend': trend,
            'used_hours': used_hours,
            'border_hits': 0,
            'template_id': template_id  # Thêm template_id vào thông tin template
        }
        
        # Cập nhật thống kê
        self.compression_stats['template_misses'] += 1
        self.compression_stats['total_blocks'] += 1
        
        return template_id

    def find_matching_template(self, data: np.ndarray, timestamp) -> Tuple[int, str, float]:
        pass

    def update_template(self, pattern_type: str, template_id: int, timestamp, cer=None, data=None) -> None:
        pass

    def optimize_template(self, pattern_type, template_id):
        pass

    def adjust_block_size(self):
        """
        Điều chỉnh kích thước block dựa trên hiệu suất nén và xu hướng dữ liệu
        """
        if not self.config['adaptive_block_size']:
            return
            
        if self.compression_stats['total_blocks'] < self.config['min_blocks_before_adjustment']:
            return
            
        # Tính toán hit ratio hiện tại
        current_hit_ratio = self.compression_stats['template_hits'] / self.compression_stats['total_blocks']
        
        # Cập nhật hit ratio cửa sổ
        self.window_blocks += 1
        if self.compression_stats['template_hits'] > 0:
            self.window_hit_count += 1
            
        # Nếu đủ kích thước cửa sổ, tính toán hit ratio mới
        if self.window_blocks >= self.config['window_size']:
            window_hit_ratio = self.window_hit_count / self.window_blocks
            self.continuous_hit_ratio.append(window_hit_ratio)
            self.window_hit_count = 0
            self.window_blocks = 0
            
        # Lấy hit ratio gần đây nhất
        recent_hit_ratio = self.continuous_hit_ratio[-1] if self.continuous_hit_ratio else current_hit_ratio
        
        # Lấy điểm tương đồng trung bình gần đây
        recent_similarity = np.mean(self.similarity_scores[-5:]) if len(self.similarity_scores) >= 5 else 1.0
        
        # ĐÁNH GIÁ ỔN ĐỊNH
        if self.in_stabilization_phase:
            self.stability_hit_ratios.append(recent_hit_ratio)
            if len(self.stability_hit_ratios) > self.stability_window_size:
                self.stability_hit_ratios = self.stability_hit_ratios[-self.stability_window_size:]
        
        # Kiểm tra ổn định của kích thước block hiện tại
        if self.stable_block_size == self.block_size:
            self.stable_periods += 1
            
            # Tăng điểm ổn định nếu hiệu suất tốt
            hit_ratio_good = recent_hit_ratio >= 0.55
            similarity_good = recent_similarity >= 0.6
            
            if hit_ratio_good and similarity_good:
                # Tăng điểm ổn định, nhưng chậm dần khi điểm cao
                increase_amount = max(1, int((self.max_stability_score - self.stability_score) * 0.1))
                self.stability_score = min(self.max_stability_score, self.stability_score + increase_amount)
            elif hit_ratio_good or similarity_good:
                # Tăng chậm hơn nếu chỉ một trong hai chỉ số tốt
                self.stability_score = min(self.max_stability_score, self.stability_score + 1)
            else:
                # Giảm điểm ổn định nếu hiệu suất không tốt
                self.stability_score = max(0, self.stability_score - 2)
        else:
            # Reset giai đoạn ổn định khi kích thước block thay đổi
            self.stable_block_size = self.block_size
            self.stable_periods = 1
            self.stability_score = 20
            self.in_stabilization_phase = False
            self.stability_hit_ratios = []
            
        # Xác định trạng thái ổn định
        if self.stable_periods >= self.stability_threshold and self.stability_score >= 50:
            self.in_stabilization_phase = True
            
            # Kiểm tra hiệu suất để duy trì ổn định
            if not self.stability_hit_ratios or np.mean(self.stability_hit_ratios) >= 0.5:
                logger.debug(f"Ổn định kích thước block tại {self.block_size} (score: {self.stability_score})")
                
                # Bỏ qua điều chỉnh nếu điểm ổn định cao
                if self.stability_score > 80:
                    if self.compression_stats['total_blocks'] - self.last_adjustment_block < self.min_adjustment_interval * 2:
                        return
                        
        # Kiểm tra khoảng cách tối thiểu giữa các lần điều chỉnh
        if self.compression_stats['total_blocks'] - self.last_adjustment_block < self.min_adjustment_interval:
            return
            
        old_size = self.block_size
        new_size = old_size
        
        # Điều chỉnh kích thước block dựa trên hit ratio và similarity
        if recent_hit_ratio > 0.6 and recent_similarity > 0.7:
            # Tăng kích thước block khi hiệu suất tốt
            new_size = min(int(old_size * 1.2), self.config['max_block_size'])
        elif recent_hit_ratio < 0.4 or recent_similarity < 0.5:
            # Giảm kích thước block khi hiệu suất kém
            new_size = max(int(old_size * 0.8), self.config['min_block_size'])
            
        if new_size != old_size:
            # Lưu lịch sử thay đổi kích thước block
            self.block_size_history.append({
                'block_number': self.compression_stats['total_blocks'],
                'old_size': old_size,
                'new_size': new_size,
                'hit_ratio': recent_hit_ratio,
                'similarity': recent_similarity
            })
            
            self.block_size = new_size
            self.last_adjustment_block = self.compression_stats['total_blocks']
            logger.info(f"Điều chỉnh kích thước block từ {old_size} thành {new_size}")
            
    def normalize_data(self, data: np.ndarray) -> np.ndarray:
        """
        Chuẩn hóa dữ liệu về khoảng [0, 1]
        
        Args:
            data: Dữ liệu cần chuẩn hóa
            
        Returns:
            Dữ liệu đã chuẩn hóa
        """
        min_val = np.min(data)
        max_val = np.max(data)
        if max_val == min_val:
            return np.zeros_like(data)
        return (data - min_val) / (max_val - min_val)
        
    def ks_exchangeable(self, block1, block2):
        # Chuẩn hóa về mean/scale trước khi so sánh
        block1_norm = (block1 - np.mean(block1)) / (np.std(block1) if np.std(block1) > 0 else 1)
        block2_norm = (block2 - np.mean(block2)) / (np.std(block2) if np.std(block2) > 0 else 1)
        stat, p_value = stats.ks_2samp(block1_norm, block2_norm)
        # self.logger.info(f"[DEBUG] KS test (normalized): p_value={p_value:.4f}, block_norm={block1_norm.tolist()}, buf_norm={block2_norm.tolist()}")
        return p_value > self.config['similarity_threshold']

    def encode_block(self, block):
        miss_debug_info = []
        for idx, buf in enumerate(self.buffers):
            block_norm = (block - np.mean(block)) / (np.std(block) if np.std(block) > 0 else 1)
            buf_norm = (buf - np.mean(buf)) / (np.std(buf) if np.std(buf) > 0 else 1)
            stat, p_value = stats.ks_2samp(block_norm, buf_norm)
            miss_debug_info.append(f"idx={idx}, p_value={p_value:.4f}")
            if self.ks_exchangeable(block, buf):
                self.encoded_stream.append(idx)
                # self.logger.debug(f"[HIT][ENCODE_BLOCK] Sử dụng buffer idx={idx}, block={block.tolist()}")
                return
        if len(self.buffers) < self.config['num_buffers']:
            self.buffers.append(block.copy())
            # self.logger.debug(f"[MISS][ENCODE_BLOCK] Thêm buffer idx={len(self.buffers)-1}, block={block.tolist()}, buffers={self.buffers}")
        else:
            self.encoded_stream.append(self.BUFFER_OVERWRITE_MARKER)
            overwrite_idx = 0  # FIFO: luôn ghi đè buffer đầu tiên
            self.encoded_stream.append(overwrite_idx)
            # self.logger.debug(f"[MISS][ENCODE_BLOCK] Ghi đè buffer idx={overwrite_idx}, block={block.tolist()}, buffers={self.buffers}")
            self.buffers[overwrite_idx] = block.copy()
        self.encoded_stream.append(0xFD)
        self.encoded_stream.append(block.copy())
        # self.logger.debug(f"[MISS][ENCODE_BLOCK] Ghi block gốc vào stream, block={block.tolist()}")

    def change_block_size(self, new_size):
        self.encoded_stream.append(self.BLOCKSIZE_CHANGE_MARKER)
        self.encoded_stream.append(new_size)
        self.logger.info(f"[BLOCKSIZE_CHANGE] Đổi block_size sang {new_size}, flush buffer")
        self.block_size = new_size
        self.buffers = []

    def simulate_compress(self, data, block_size, num_buffers, similarity_threshold):
        buffers = []
        encoded_stream = []
        hit_count = 0
        for i in range(0, len(data), block_size):
            block = data[i:i+block_size]
            matched = False
            for idx, buf in enumerate(buffers):
                stat, p_value = stats.ks_2samp(block, buf)
                if p_value > similarity_threshold:
                    encoded_stream.append(idx)
                    hit_count += 1
                    matched = True
                    break
            if not matched:
                if len(buffers) < num_buffers:
                    buffers.append(block.copy())
                else:
                    encoded_stream.append(self.BUFFER_OVERWRITE_MARKER)
                    overwrite_idx = 0
                    encoded_stream.append(overwrite_idx)
                    buffers[overwrite_idx] = block.copy()
                encoded_stream.append(block.copy())
        compression_ratio = len(data) / max(1, len(encoded_stream))
        return compression_ratio, hit_count

    def multistage_blocksize_sampling(self, data):
        import random
        import numpy as np
        min_n = self.config['min_block_size']
        max_n = self.config['max_block_size']
        window = self.config.get('sampling_window', 5)
        trials = self.config.get('sampling_trials', 2)
        denial_window = self.config.get('denial_window', 2)
        best_n = self.block_size
        best_score = -1
        n_candidates = list(range(min_n, max_n+1, max(1, (max_n-min_n)//window)))
        for t in range(trials):
            results = []
            for n in n_candidates:
                ratio, hit = self.simulate_compress(data, n, self.config['num_buffers'], self.config['similarity_threshold'])
                num_blocks = len(data) // n if n > 0 else 1
                hit_ratio = hit / num_blocks if num_blocks > 0 else 0.0
                results.append((n, hit_ratio, ratio))
            n_arr = np.array([x[0] for x in results])
            h_arr = np.array([x[1] for x in results])
            r_arr = np.array([x[2] for x in results])
            idx_best = np.argmax(h_arr)  # Ưu tiên hit ratio cao nhất
            best_n = n_arr[idx_best]
            best_score = h_arr[idx_best]
            self.logger.info(f"[BLOCKSIZE_SAMPLING][Trial {t+1}] n={n_arr.tolist()}, hit_ratio={h_arr.round(4).tolist()}, ratio={r_arr.round(4).tolist()}, tốt nhất: n={int(best_n)}, hit_ratio={best_score:.4f}")
            n_candidates = list(range(max(min_n, best_n-window), min(max_n, best_n+window)+1))
        if abs(best_n - self.block_size) > denial_window:
            self.logger.info(f"[BLOCKSIZE_SAMPLING] Đề xuất đổi block size từ {self.block_size} -> {int(best_n)} (hit_ratio={best_score:.4f})")
            return int(best_n)
        else:
            self.logger.info(f"[BLOCKSIZE_SAMPLING] Không đổi block size (n đề xuất={int(best_n)}, denial window ±{denial_window})")
            return self.block_size

    def compress(self, data: np.ndarray, timestamps=None) -> Dict:
        # print("Dữ liệu gốc:", data[:self.block_size].tolist())
        self.encoded_stream = []
        self.buffers = []
        hit_count = 0
        total_blocks = 0
        self.recent_data = []  # Reset recent_data mỗi lần nén mới
        interval = self.config.get('sampling_interval', 10)
        for i in range(0, len(data), self.block_size):
            block = data[i:i+self.block_size]
            self.recent_data.extend(block.tolist())
            if len(self.recent_data) > self.config['sampling_recent_size']:
                self.recent_data = self.recent_data[-self.config['sampling_recent_size']:]
            matched = False
            for idx, buf in enumerate(self.buffers):
                block_norm = (block - np.mean(block)) / (np.std(block) if np.std(block) > 0 else 1)
                buf_norm = (buf - np.mean(buf)) / (np.std(buf) if np.std(buf) > 0 else 1)
                stat, p_value = stats.ks_2samp(block_norm, buf_norm)
                if p_value > self.config['similarity_threshold']:
                    hit_count += 1
                    matched = True
                    break
            total_blocks += 1
            self.encode_block(block)
            # Sampling block size linh hoạt: từ block thứ 3 trở đi, lặp lại mỗi interval block
            if total_blocks >= 3 and total_blocks % interval == 0:
                # Nếu tổng số block nhỏ, sampling trên toàn bộ recent_data
                if total_blocks < 100:
                    sample_data = np.array(self.recent_data)
                else:
                    sample_data = np.array(self.recent_data[-self.config['sampling_recent_size']:])
                n_opt = self.multistage_blocksize_sampling(sample_data)
                if n_opt != self.block_size:
                    self.logger.info(f"[BLOCKSIZE_CHANGE] Đổi block size từ {self.block_size} -> {n_opt} tại block {total_blocks}")
                    self.change_block_size(n_opt)
        hit_ratio = hit_count / total_blocks if total_blocks > 0 else 0.0
        compression_ratio = 0  # Đặt compression_ratio = 0, sẽ tính sau khi lưu vào DB
        self.logger.info(f"[SUMMARY] Tổng số block: {total_blocks}, Hit: {hit_count}, Hit ratio: {hit_ratio:.4f}")
        return {
            'encoded_stream': self.encoded_stream,
            'block_size': self.block_size,
            'num_buffers': self.config['num_buffers'],
            'original_length': len(data),
            'hit_ratio': hit_ratio,
            'compression_ratio': compression_ratio
        } 