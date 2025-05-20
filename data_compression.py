#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import logging
import numpy as np
from scipy import stats

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataCompressor:

    def __init__(self, config=None):
        """
        Khởi tạo compressor với các cấu hình mặc định
        
        Args:
            config: Dict chứa các tham số cấu hình
        """
        # Cấu hình mặc định
        self.config = {
            'p_threshold': 0.1,       # Ngưỡng p-value cho KS test
            'max_templates': 200,     # Số lượng template tối đa
            'min_values': 10,         # Số lượng giá trị tối thiểu để xem xét
            'min_block_size': 10,     # Kích thước block tối thiểu
            'max_block_size': 100,    # Kích thước block tối đa
            'adaptive_block_size': True, # Tự động điều chỉnh kích thước block
            'min_blocks_before_adjustment': 5, # Số block tối thiểu trước khi điều chỉnh
            'confidence_level': 0.95, # Mức độ tin cậy
            'pmin': 0.5,             # Xác suất tối thiểu để xem xét block khớp với template
            'block_size': 10,        # Kích thước block ban đầu
            'w1': 0.6,               # Trọng số cho CER trong cost function
            'w2': 0.4,               # Trọng số cho CR trong cost function
            'max_acceptable_cer': 0.15, # Ngưỡng CER tối đa chấp nhận được
            'correlation_threshold': 0.6, # Ngưỡng tương quan Pearson
            'similarity_weights': {   # Trọng số cho các phương pháp so sánh
                'ks_test': 0.2,      # Trọng số cho KS test
                'correlation': 0.5,   # Trọng số cho tương quan Pearson 
                'cer': 0.3           # Trọng số cho CER
            },
            'template_expiration': 300,  # Số block tối đa không dùng trước khi hết hạn
            'template_usage_threshold': 1,  # Số lần sử dụng tối thiểu để giữ template
            'max_template_age': 150,  # Tuổi tối đa của template
            'trend_detection_window': 5,  # Số block để phát hiện xu hướng
            'trend_threshold': 0.7,  # Ngưỡng để xác định xu hướng
            'template_merge_threshold': 0.9,  # Ngưỡng tương đồng để gộp template
            'template_merge_interval': 20     # Số block giữa các lần kiểm tra gộp
        }
        
        # Cập nhật cấu hình nếu được cung cấp
        if config:
            self.config.update(config)
            
        self.reset()
        logger.info(f"Khởi tạo Data Compressor với cấu hình: {self.config}")
        
        self.template_threshold = 0.95  # Ngưỡng tương đồng cao hơn cho non-loss
        self.block_size = 1000  # Kích thước block nhỏ hơn để tăng độ chính xác
        self.max_templates = 1000  # Giới hạn số lượng template
        self.template_cache = {}  # Cache để lưu các template đã tìm thấy
        
    def reset(self):
        """
        Reset trạng thái của compressor
        """
        # Khởi tạo các tham số của thuật toán
        self.templates = {}                # Dict lưu trữ các template
        self.template_counter = 0          # Bộ đếm template để tạo ID
        self.encoded_stream = []           # Danh sách các mã nén
        self.current_block_size = self.config['block_size']  # Kích thước block hiện tại
        self.blocks_processed = 0          # Số lượng block đã xử lý
        self.template_hit_count = 0        # Số lần tìm thấy template phù hợp
        self.templates_used = set()        # Tập hợp các template đã sử dụng
        self.recent_values = []            # Các giá trị gần đây để phát hiện xu hướng
        self.block_size_history = []       # Lịch sử thay đổi kích thước block
        self.cer_values = []               # Lịch sử các giá trị CER
        self.similarity_scores = []        # Lịch sử các điểm tương đồng
        self.cost_values = []              # Lịch sử các giá trị cost
        self.template_stats = {}           # Thống kê về các template
        self.template_usage = {}           # Số lần template được sử dụng
        self.template_last_used = {}       # Block cuối cùng template được sử dụng
        self.template_creation_time = {}   # Block khi template được tạo
        self.continuous_hit_ratio = []     # Theo dõi hit ratio liên tục theo thời gian
        self.hit_ratio_by_block = []       # Thêm biến này để lưu hit ratio theo block
        self.window_hit_count = 0          # Đếm hit trong cửa sổ hiện tại
        self.window_blocks = 0             # Đếm blocks trong cửa sổ hiện tại
        self.window_size = 10              # Kích thước cửa sổ để tính hit ratio động
        self.previous_adjustments = []     # Lịch sử các điều chỉnh trước đó
        self.min_adjustment_interval = 3   # Số block tối thiểu giữa các lần điều chỉnh
        self.last_adjustment_block = 0     # Block cuối cùng được điều chỉnh
        self.last_merge_check = 0          # Block cuối cùng kiểm tra gộp template
        self.merged_templates = {}         # Dict lưu thông tin template đã gộp
        self.template_importance = {}      # Dict lưu tầm quan trọng của các template
        
        # Các biến mới để theo dõi sự ổn định của kích thước block
        self.stable_block_size = None      # Kích thước block được xác định là ổn định
        self.stable_periods = 0            # Số chu kỳ mà block size giữ ổn định
        self.stability_threshold = 5       # Ngưỡng số chu kỳ để coi là ổn định
        self.stability_score = 0           # Điểm ổn định hiện tại (0-100)
        self.in_stabilization_phase = False # Đang trong giai đoạn ổn định
        self.stability_hit_ratios = []     # Lịch sử hit ratio khi đã ổn định
        self.stability_window_size = 10    # Kích thước cửa sổ để theo dõi hit ratio ổn định
        self.max_stability_score = 100     # Điểm ổn định tối đa

        logger.info("Đã reset Data Compressor")
        
    def update_template_metrics(self, template_id, used=True):
        """
        Cập nhật các chỉ số sử dụng của template
        
        Args:
            template_id: ID của template cần cập nhật
            used: True nếu template được sử dụng, False nếu chỉ kiểm tra
        """
        # Khởi tạo chỉ số nếu là template mới
        if template_id not in self.template_usage:
            self.template_usage[template_id] = 0
            self.template_creation_time[template_id] = self.blocks_processed
            
            # CẢI TIẾN: Thêm lưu vết lịch sử sử dụng
            if not hasattr(self, 'template_usage_history'):
                self.template_usage_history = {}
            self.template_usage_history[template_id] = []
            
            # CẢI TIẾN: Thêm theo dõi thành công của template
            if not hasattr(self, 'template_success_rate'):
                self.template_success_rate = {}
            self.template_success_rate[template_id] = {'hits': 0, 'checks': 0}
            
            # CẢI TIẾN: Theo dõi điểm sử dụng theo thời gian
            if not hasattr(self, 'template_quality_scores'):
                self.template_quality_scores = {}
            self.template_quality_scores[template_id] = 1.0  # Khởi tạo điểm chất lượng ban đầu
        
        # Cập nhật số lần sử dụng và thời gian sử dụng gần nhất
        if used:
            self.template_usage[template_id] += 1
            
            # CẢI TIẾN: Cập nhật lịch sử sử dụng
            if hasattr(self, 'template_usage_history'):
                # Lưu block sử dụng và cập nhật hit ratio tại thời điểm đó
                current_hit_ratio = self.template_hit_count / max(1, self.blocks_processed)
                self.template_usage_history[template_id].append({
                    'block': self.blocks_processed,
                    'hit_ratio': current_hit_ratio
                })
                
                # Giới hạn kích thước lịch sử
                max_history = 10
                if len(self.template_usage_history[template_id]) > max_history:
                    self.template_usage_history[template_id] = self.template_usage_history[template_id][-max_history:]
            
            # CẢI TIẾN: Cập nhật tỷ lệ thành công
            if hasattr(self, 'template_success_rate'):
                self.template_success_rate[template_id]['hits'] += 1
                self.template_success_rate[template_id]['checks'] += 1
                
                # Tăng điểm chất lượng khi template được sử dụng thành công
                if hasattr(self, 'template_quality_scores'):
                    # Tính tỷ lệ thành công
                    success_rate = self.template_success_rate[template_id]['hits'] / max(1, self.template_success_rate[template_id]['checks'])
                    
                    # Tăng điểm chất lượng nhưng giới hạn ở mức 5.0
                    quality_bonus = min(0.1, 0.05 * success_rate)  # Tối đa +0.1 mỗi lần sử dụng
                    self.template_quality_scores[template_id] = min(5.0, self.template_quality_scores[template_id] + quality_bonus)
        else:
            # CẢI TIẾN: Cập nhật số lần kiểm tra
            if hasattr(self, 'template_success_rate'):
                self.template_success_rate[template_id]['checks'] += 1
                
        self.template_last_used[template_id] = self.blocks_processed
        
        # CẢI TIẾN: Giảm điểm chất lượng của template ít được sử dụng
        if hasattr(self, 'template_quality_scores') and self.blocks_processed % 10 == 0:
            # Cập nhật điểm tất cả template mỗi 10 block
            for tid in list(self.template_quality_scores.keys()):
                if tid in self.templates:  # Đảm bảo template vẫn tồn tại
                    # Xác định thời gian không sử dụng
                    unused_time = self.blocks_processed - self.template_last_used.get(tid, 0)
                    
                    if unused_time > 20:  # Giảm điểm nếu >20 block không sử dụng
                        # Giảm điểm nhanh hơn khi thời gian không sử dụng càng lâu
                        decay_rate = min(0.2, 0.02 * (unused_time / 10))  # Tối đa -0.2 mỗi lần cập nhật
                        self.template_quality_scores[tid] = max(0.1, self.template_quality_scores[tid] - decay_rate)
    
    def detect_trend(self, data):
        """
        Phát hiện xu hướng trong dữ liệu gần đây
        
        Args:
            data: Dữ liệu hiện tại (mảng numpy 1D)
            
        Returns:
            tuple: (has_trend, trend_type, trend_strength)
                has_trend: True nếu có xu hướng rõ ràng
                trend_type: 1 (tăng), -1 (giảm), 0 (không xác định)
                trend_strength: Độ mạnh của xu hướng (0-1)
        """
        # Thêm dữ liệu mới vào danh sách giá trị gần đây
        data_mean = np.mean(data)
        self.recent_values.append(data_mean)
        
        # Giữ kích thước cửa sổ phát hiện xu hướng
        window_size = self.config['trend_detection_window']
        if len(self.recent_values) > window_size:
            self.recent_values = self.recent_values[-window_size:]
        
        # Cần ít nhất 3 giá trị để phát hiện xu hướng
        if len(self.recent_values) < 3:
            return False, 0, 0.0
        
        # Tính xu hướng bằng hệ số góc của đường hồi quy tuyến tính
        x = np.arange(len(self.recent_values))
        y = np.array(self.recent_values)
        slope, _, r_value, _, _ = stats.linregress(x, y)
        
        # Tính độ mạnh của xu hướng dựa trên hệ số tương quan
        trend_strength = abs(r_value)
        
        # Xác định loại xu hướng
        if trend_strength > self.config['trend_threshold']:
            trend_type = 1 if slope > 0 else -1
            return True, trend_type, trend_strength
        
        return False, 0, trend_strength
    
    def clean_expired_templates(self):
        """
        Loại bỏ các template không còn sử dụng hoặc hết hạn
        
        Returns:
            int: Số template đã loại bỏ
        """
        # Trước tiên, thử gộp các template tương tự
        if (self.config.get('enable_template_merging', True) and 
            self.blocks_processed - self.last_merge_check >= self.config.get('template_merge_interval', 20)):
            self.merge_similar_templates()
            self.last_merge_check = self.blocks_processed
        
        # CẢI TIẾN: Điều chỉnh ngưỡng dọn dẹp
        # Không làm gì nếu số template chưa vượt ngưỡng cao hơn
        if len(self.templates) <= self.config['max_templates'] * 0.85:  # Giảm từ 0.9 xuống 0.85
            return 0
        
        templates_to_remove = []
        current_block = self.blocks_processed
        
        # Tính toán tầm quan trọng của mỗi template
        self.calculate_template_importance()
        
        # CẢI TIẾN: Đánh giá template dựa trên nhiều yếu tố hơn
        template_scores = []
        
        # Đánh giá từng template
        for template_id in list(self.templates.keys()):
            # Tính tuổi của template (số block từ khi tạo)
            template_age = current_block - self.template_creation_time.get(template_id, 0)
            
            # Tính thời gian không sử dụng
            unused_time = current_block - self.template_last_used.get(template_id, 0)
            
            # Tính số lần sử dụng
            usage_count = self.template_usage.get(template_id, 0)
            
            # Lấy điểm quan trọng
            importance = self.template_importance.get(template_id, 0)
            
            # CẢI TIẾN: Sử dụng điểm chất lượng nếu có
            quality_score = 1.0  # Giá trị mặc định
            if hasattr(self, 'template_quality_scores'):
                quality_score = self.template_quality_scores.get(template_id, 1.0)
            
            # CẢI TIẾN: Tính tỷ lệ thành công
            success_rate = 0.5  # Giá trị mặc định
            if hasattr(self, 'template_success_rate'):
                if template_id in self.template_success_rate:
                    hits = self.template_success_rate[template_id]['hits']
                    checks = self.template_success_rate[template_id]['checks']
                    if checks > 0:
                        success_rate = hits / checks
            
            # CẢI TIẾN: Tính điểm bảo vệ cho template
            protection_score = (
                0.3 * importance +                                # Quan trọng từ các tiêu chí cũ
                0.25 * quality_score / 5.0 +                      # Điểm chất lượng (0-5 -> 0-1)
                0.2 * min(1.0, usage_count / 10) +                # Số lần sử dụng (tối đa 10)
                0.15 * success_rate +                             # Tỷ lệ thành công (0-1)
                0.1 * max(0, 1 - unused_time / max(1, self.config['template_expiration']))  # Thời gian sử dụng gần đây
            )
            
            # Có thể bị loại bỏ nếu:
            removal_candidate = False
            
            # CẢI TIẾN: Điều kiện loại bỏ thông minh hơn
            # 1. Template lâu không sử dụng và tuổi cao
            if (unused_time > self.config['template_expiration'] * 0.9 and  # Giảm từ 1.0 xuống 0.9
                template_age > self.config['max_template_age'] * 0.8):
                removal_candidate = True
                
            # 2. Template có rất ít lần sử dụng và đã tồn tại rất lâu
            elif (usage_count <= self.config['template_usage_threshold'] and 
                  template_age > self.config['max_template_age'] * 0.9):
                removal_candidate = True
                
            # 3. Template đã quá cũ (vượt quá tuổi tối đa) và ít sử dụng
            elif (template_age > self.config['max_template_age'] and usage_count < 4):  # Tăng từ 3 lên 4
                removal_candidate = True
                
            # 4. CẢI TIẾN: Template có tỷ lệ thành công thấp nếu kiểm tra nhiều lần
            elif (hasattr(self, 'template_success_rate') and 
                  self.template_success_rate[template_id]['checks'] > 15 and 
                  success_rate < 0.2):
                removal_candidate = True
                
            # 5. CẢI TIẾN: Template có điểm chất lượng thấp và ít dùng
            elif (hasattr(self, 'template_quality_scores') and 
                  quality_score < 0.5 and 
                  usage_count < 3 and 
                  template_age > 30):
                removal_candidate = True
            
            # Nếu là ứng viên loại bỏ, thêm vào danh sách với điểm bảo vệ
            if removal_candidate:
                template_scores.append((template_id, protection_score))
        
        # Sắp xếp tăng dần theo điểm bảo vệ (điểm thấp hơn sẽ bị loại bỏ trước)
        template_scores.sort(key=lambda x: x[1])
        
        # CẢI TIẾN: Chỉ chọn templates có điểm thấp nhất trong số ứng viên loại bỏ
        templates_to_remove = [tid for tid, _ in template_scores]
        
        # CẢI TIẾN: Xóa ít template hơn mỗi lần
        # Chỉ xóa 5% số lượng template hiện có hoặc tối đa 3 template
        max_templates_to_remove = self.config.get('max_templates_to_remove_percent', 0.05)
        num_to_remove = min(len(templates_to_remove), 
                         max(1, min(3, int(len(self.templates) * max_templates_to_remove))))
        
        # CẢI TIẾN: Bảo vệ template có điểm bảo vệ cao
        final_remove_list = []
        for tid, score in template_scores[:num_to_remove]:
            # Bảo vệ template có điểm cao hơn 0.7
            if score > 0.7:
                logger.debug(f"Bảo vệ template {tid} mặc dù là ứng viên loại bỏ (điểm bảo vệ: {score:.3f})")
                continue
            final_remove_list.append(tid)
        
        # Nếu cuối cùng không có template nào bị xóa, chọn một template điểm thấp nhất
        if not final_remove_list and template_scores:
            final_remove_list = [template_scores[0][0]]
            
        # Lưu lại thông tin các template sắp bị xóa
        for template_id in final_remove_list:
            # CẢI TIẾN: Lưu thông tin chi tiết hơn về template bị xóa
            template_to_remove = self.templates[template_id]
            
            # Chuyển đổi template sang định dạng thống nhất nếu cần
            if not isinstance(template_to_remove, dict) or 'values' not in template_to_remove:
                if isinstance(template_to_remove, np.ndarray):
                    # Nếu là mảng numpy, chuyển thành dictionary
                    template_data = {
                        'id': template_id,
                        'values': template_to_remove.tolist() if hasattr(template_to_remove, 'tolist') else template_to_remove,
                        'created_at': self.template_creation_time.get(template_id, 0)
                    }
                else:
                    # Đối với các loại dữ liệu khác
                    template_data = {
                        'id': template_id,
                        'values': template_to_remove,
                        'created_at': self.template_creation_time.get(template_id, 0)
                    }
            else:
                template_data = template_to_remove
                
            # Lưu thông tin chi tiết về template
            self.merged_templates[template_id] = {
                'data': template_data,
                'usage': self.template_usage.get(template_id, 0),
                'last_used': self.template_last_used.get(template_id, 0),
                'creation_time': self.template_creation_time.get(template_id, 0),
                'importance': self.template_importance.get(template_id, 0),
                'removed_at': current_block
            }
            
            # CẢI TIẾN: Lưu thêm thông tin về chất lượng và tỷ lệ thành công
            if hasattr(self, 'template_quality_scores'):
                self.merged_templates[template_id]['quality_score'] = self.template_quality_scores.get(template_id, 1.0)
                
            if hasattr(self, 'template_success_rate'):
                if template_id in self.template_success_rate:
                    self.merged_templates[template_id]['success_rate'] = self.template_success_rate[template_id]
            
            # Ghi log chi tiết về template bị xóa
            logger.info(f"Loại bỏ template ID {template_id} (sử dụng: {self.template_usage.get(template_id, 0)}, "
                      f"tuổi: {current_block - self.template_creation_time.get(template_id, 0)} blocks, "
                      f"quan trọng: {self.template_importance.get(template_id, 0):.2f}, "
                      f"điểm bảo vệ: {next((score for tid, score in template_scores if tid == template_id), 0):.3f})")
            
            # Xóa template
            if template_id in self.templates:
                del self.templates[template_id]
                
                # Cập nhật các chỉ số liên quan
                for attr in ['template_usage', 'template_last_used', 'template_creation_time', 'template_importance']:
                    if hasattr(self, attr):
                        attr_dict = getattr(self, attr)
                        if template_id in attr_dict:
                            del attr_dict[template_id]
                
                # CẢI TIẾN: Cập nhật các thuộc tính bổ sung
                for attr in ['template_quality_scores', 'template_success_rate', 'template_usage_history']:
                    if hasattr(self, attr):
                        attr_dict = getattr(self, attr)
                        if template_id in attr_dict:
                            del attr_dict[template_id]
        
        return len(final_remove_list)
        
    def calculate_template_importance(self):
        """
        Tính toán tầm quan trọng của mỗi template dựa trên nhiều yếu tố.
        - Số lần sử dụng
        - Thời gian gần đây được sử dụng
        - Tuổi của template
        """
        current_block = self.blocks_processed
        if current_block == 0:
            return
            
        weights = self.config.get('template_importance_weight', {
            'usage_count': 0.5,
            'recency': 0.3,
            'age': 0.2
        })
        
        # Chuẩn hóa các giá trị để so sánh
        max_usage = max(self.template_usage.values()) if self.template_usage else 1
        max_age = max([current_block - creation for creation in self.template_creation_time.values()]) if self.template_creation_time else 1
        max_unused = max([current_block - last_used for last_used in self.template_last_used.values()]) if self.template_last_used else 1
        
        for template_id in self.templates:
            # Tính các thành phần điểm
            usage_score = self.template_usage.get(template_id, 0) / max_usage
            
            age = current_block - self.template_creation_time.get(template_id, 0)
            age_score = age / max_age  # Template càng cũ càng có giá trị
            
            unused_time = current_block - self.template_last_used.get(template_id, 0)
            recency_score = 1.0 - (unused_time / max_unused)  # Template càng được sử dụng gần đây càng tốt
            
            # Tính điểm tổng hợp
            importance = (
                weights.get('usage_count', 0.5) * usage_score +
                weights.get('recency', 0.3) * recency_score +
                weights.get('age', 0.2) * age_score
            )
            
            self.template_importance[template_id] = importance
    
    def merge_similar_templates(self):
        """
        Gộp các template tương tự nhau để giảm số lượng template
        và tăng khả năng tái sử dụng template.
        """
        if len(self.templates) < 5:  # Cần ít nhất 5 template để đáng xem xét việc gộp
            return 0
            
        # Ngưỡng tương đồng để gộp template
        merge_threshold = self.config.get('template_merge_threshold', 0.9)
        
        # Danh sách các cặp template có thể gộp
        merge_candidates = []
        
        # So sánh từng cặp template
        template_ids = list(self.templates.keys())
        for i in range(len(template_ids)):
            for j in range(i+1, len(template_ids)):
                id1, id2 = template_ids[i], template_ids[j]
                
                # Bỏ qua nếu một trong hai template được sử dụng quá nhiều
                if (self.template_usage.get(id1, 0) > 10 and self.template_usage.get(id2, 0) > 10):
                    continue
                    
                # Tính điểm tương đồng giữa hai template
                try:
                    similarity = self.calculate_similarity_score(self.templates[id1], self.templates[id2])
                    
                    if similarity > merge_threshold:
                        # Thêm vào danh sách gộp
                        usage1 = self.template_usage.get(id1, 0)
                        usage2 = self.template_usage.get(id2, 0)
                        
                        # Template nào được sử dụng ít hơn sẽ bị gộp vào cái được sử dụng nhiều hơn
                        if usage1 >= usage2:
                            merge_candidates.append((id2, id1, similarity))  # Gộp id2 vào id1
                        else:
                            merge_candidates.append((id1, id2, similarity))  # Gộp id1 vào id2
                except Exception as e:
                    logger.warning(f"Lỗi khi tính toán tương đồng giữa template {id1} và {id2}: {str(e)}")
        
        # Sắp xếp theo độ tương đồng giảm dần
        merge_candidates.sort(key=lambda x: x[2], reverse=True)
        
        # Danh sách template đã được xử lý (để tránh gộp nhiều lần)
        processed_templates = set()
        templates_merged = 0
        
        # Gộp các template
        for source_id, target_id, similarity in merge_candidates:
            if source_id in processed_templates or target_id in processed_templates:
                continue  # Bỏ qua nếu template đã bị gộp
                
            if source_id not in self.templates or target_id not in self.templates:
                continue  # Bỏ qua nếu template không còn tồn tại
            
            # Gộp template source vào target
            # Cập nhật số lần sử dụng
            self.template_usage[target_id] += self.template_usage.get(source_id, 0)
            
            # Cập nhật thời gian sử dụng gần nhất
            self.template_last_used[target_id] = max(
                self.template_last_used.get(target_id, 0),
                self.template_last_used.get(source_id, 0)
            )
            
            # Lưu trữ thông tin template bị gộp (để có thể tái tạo nếu cần)
            self.merged_templates[source_id] = {
                'data': self.templates[source_id],
                'usage': self.template_usage.get(source_id, 0),
                'last_used': self.template_last_used.get(source_id, 0),
                'creation_time': self.template_creation_time.get(source_id, 0),
                'merged_into': target_id
            }
            
            # Xóa template source
            del self.templates[source_id]
            if source_id in self.template_usage:
                del self.template_usage[source_id]
            if source_id in self.template_last_used:
                del self.template_last_used[source_id]
            if source_id in self.template_creation_time:
                del self.template_creation_time[source_id]
            if source_id in self.template_importance:
                del self.template_importance[source_id]
                
            # Đánh dấu đã xử lý
            processed_templates.add(source_id)
            processed_templates.add(target_id)
            templates_merged += 1
            
            logger.info(f"Đã gộp template ID {source_id} vào template ID {target_id} với độ tương đồng {similarity:.2f}")
            
            # Giới hạn số lượng template gộp mỗi lần
            if templates_merged >= 3:
                break
                
        return templates_merged
        
    def calculate_cer(self, block1: np.ndarray, block2: np.ndarray) -> float:
        """
        Tính Compression Error Rate giữa hai block
        
        Args:
            block1: Block dữ liệu thứ nhất
            block2: Block dữ liệu thứ hai
        
        Returns:
            float: Giá trị CER từ 0 đến 1
        """
        try:
            if len(block1) != len(block2):
                return 1.0

            # Tính MSE
            mse = np.mean((block1 - block2) ** 2)
            
            # Chuẩn hóa MSE về khoảng [0, 1]
            max_val = max(np.max(block1), np.max(block2))
            min_val = min(np.min(block1), np.min(block2))
            range_val = max(1.0, max_val - min_val)  # Tránh chia cho 0
            
            # Tính CER và giới hạn trong khoảng [0, 1]
            cer = min(1.0, mse / (range_val ** 2))
            
            return cer

        except Exception as e:
            logger.error(f"Lỗi khi tính CER: {str(e)}")
            return 1.0
    
    def calculate_correlation(self, data1, data2):
        """
        Tính hệ số tương quan Pearson giữa hai mảng dữ liệu
        
        Phiên bản nâng cao hỗ trợ dữ liệu đa chiều.
        
        Args:
            data1, data2: Hai đối tượng dữ liệu cần so sánh (mảng 1D hoặc dictionary)
            
        Returns:
            float: Hệ số tương quan [0, 1] (1 là tương quan hoàn hảo)
        """
        # Trường hợp dữ liệu đa chiều
        if self.multi_dimensional and isinstance(data1, dict) and isinstance(data2, dict):
            total_corr = 0.0
            total_weight = 0.0
            dimension_weights = self.config.get('dimension_weights', {})
            
            # Tính tương quan cho từng chiều dữ liệu
            for dim in data1.keys():
                if dim in data2:
                    # Lấy trọng số cho chiều này, mặc định là 1.0
                    weight = dimension_weights.get(dim, 1.0)
                    if weight > 0:
                        try:
                            # Tính tương quan cho chiều này
                            values1 = np.array(data1[dim])
                            values2 = np.array(data2[dim])
                            
                            # Đảm bảo dữ liệu có cùng kích thước
                            min_len = min(len(values1), len(values2))
                            x = values1[:min_len]
                            y = values2[:min_len]
                            
                            # Tính hệ số tương quan Pearson
                            corr, _ = stats.pearsonr(x, y)
                            
                            # Chuyển sang giá trị tuyệt đối và chuẩn hóa về [0, 1]
                            dim_corr = abs(corr)
                            
                            # Cộng vào tổng có trọng số
                            total_corr += dim_corr * weight
                            total_weight += weight
                        except Exception as e:
                            logger.warning(f"Lỗi khi tính hệ số tương quan cho chiều {dim}: {str(e)}")
            
            # Trả về giá trị tương quan trung bình có trọng số
            if total_weight > 0:
                return total_corr / total_weight
            return 0.0
            
        # Trường hợp dữ liệu một chiều - giữ nguyên code cũ
        try:
            # Đảm bảo dữ liệu có cùng kích thước
            min_len = min(len(data1), len(data2))
            x = np.array(data1[:min_len])
            y = np.array(data2[:min_len])
            
            # Tính hệ số tương quan Pearson
            corr, _ = stats.pearsonr(x, y)
            
            # Chuyển sang giá trị tuyệt đối và chuẩn hóa về [0, 1]
            return abs(corr)
        except Exception as e:
            logger.warning(f"Lỗi khi tính hệ số tương quan: {str(e)}")
            return 0.0
    
    def calculate_cost(self, cer, cr):
        """
        Tính cost function cân bằng giữa CER và CR
        
        Cost = w1 * CER - w2 * CR, trong đó:
        - w1, w2 là trọng số (w1 + w2 = 1)
        - Giá trị cost càng thấp càng tốt
        
        Args:
            cer: Compression Error Rate
            cr: Compression Ratio
        
        Returns:
            float: Giá trị cost function
        """
        w1 = self.config['w1']
        w2 = self.config['w2']
        
        # Chuẩn hóa CER và CR để chúng có cùng thang đo
        # Giả sử CER trong khoảng [0, max_acceptable_cer] và CR trong khoảng [1, ∞)
        normalized_cer = min(1.0, cer / self.config['max_acceptable_cer'])
        normalized_cr = min(1.0, 1.0 / cr)  # CR càng lớn, normalized_cr càng nhỏ
        
        # Tính cost (giá trị càng thấp càng tốt)
        return w1 * normalized_cer - w2 * (1 - normalized_cr)
    
    def calculate_similarity_score(self, data1, data2):

        # Trường hợp dữ liệu đa chiều (dictionary)
        if self.multi_dimensional and isinstance(data1, dict) and isinstance(data2, dict):
            total_similarity = 0.0
            total_weight = 0.0
            dimension_weights = self.config.get('dimension_weights', {})
            
            # Dictionary lưu các chỉ số chi tiết cho từng chiều
            dimension_details = {}
            
            # Tính các chỉ số tổng hợp
            ks_pvalue = 0.0
            correlation = self.calculate_correlation(data1, data2)  # Đã hỗ trợ đa chiều
            cer = self.calculate_cer(data1, data2)  # Đã hỗ trợ đa chiều
            
            # Chuẩn hóa CER
            normalized_cer = 1.0 - min(1.0, cer / self.config['max_acceptable_cer'])
            
            # Tính điểm tương đồng cho từng chiều dữ liệu
            dimensions_processed = 0
            
            for dim in data1.keys():
                if dim in data2:
                    # Lấy trọng số cho chiều này, mặc định là 1.0
                    weight = dimension_weights.get(dim, 1.0)
                    if weight > 0:
                        values1 = np.array(data1[dim])
                        values2 = np.array(data2[dim])
                        
                        # Đảm bảo dữ liệu có cùng kích thước
                        min_len = min(len(values1), len(values2))
                        values1 = values1[:min_len]
                        values2 = values2[:min_len]
                        
                        try:
                            # Tính P-value từ KS test cho chiều này
                            dim_ks, dim_ks_pvalue = stats.ks_2samp(values1, values2)
                            ks_pvalue += dim_ks_pvalue * weight
                            
                            # Chuẩn hóa dữ liệu để so sánh hình dạng
                            values1_norm = (values1 - np.mean(values1)) / (np.std(values1) if np.std(values1) > 0 else 1)
                            values2_norm = (values2 - np.mean(values2)) / (np.std(values2) if np.std(values2) > 0 else 1)
                            
                            # Độ lệch trung bình giữa hai đường chuẩn hóa
                            shape_diff = np.mean(np.abs(values1_norm - values2_norm))
                            shape_similarity = max(0, 1 - min(1, shape_diff/3.0))
                            
                            # So sánh biến thiên (trend) theo thời gian
                            grad1 = np.diff(values1_norm)
                            grad2 = np.diff(values2_norm)
                            
                            if len(grad1) > 0 and len(grad2) > 0:
                                min_grad_len = min(len(grad1), len(grad2))
                                grad1 = grad1[:min_grad_len]
                                grad2 = grad2[:min_grad_len]
                                
                                # Đếm số lần gradient có cùng dấu (cùng chiều tăng/giảm)
                                same_direction = np.sum((grad1 * grad2) > 0)
                                trend_similarity = same_direction / min_grad_len if min_grad_len > 0 else 0
                            else:
                                trend_similarity = 0
                            
                            # Lưu thông tin chi tiết cho chiều này
                            dimension_details[dim] = {
                                'ks_pvalue': dim_ks_pvalue,
                                'shape_similarity': shape_similarity,
                                'trend_similarity': trend_similarity,
                                'weight': weight
                            }
                            
                            # Cộng dồn trọng số đã xử lý
                            total_weight += weight
                            dimensions_processed += 1
                            
                        except Exception as e:
                            logger.warning(f"Lỗi khi tính điểm tương đồng cho chiều {dim}: {str(e)}")
            
            # Chuẩn hóa ks_pvalue theo trọng số
            if total_weight > 0:
                ks_pvalue = ks_pvalue / total_weight
            
            # Lấy trọng số từ cấu hình
            weights = {
                'ks_test': 0.15,
                'correlation': 0.25,
                'cer': 0.15,
                'shape': 0.25,
                'trend': 0.20
            }
            
            # Ghi đè trọng số từ cấu hình nếu có
            if 'enhanced_similarity_weights' in self.config:
                weights.update(self.config['enhanced_similarity_weights'])
            
            # Tính các thành phần tương đồng tổng hợp
            avg_shape_similarity = sum(detail['shape_similarity'] * detail['weight'] 
                                    for detail in dimension_details.values()) / total_weight if total_weight > 0 else 0
            
            avg_trend_similarity = sum(detail['trend_similarity'] * detail['weight'] 
                                    for detail in dimension_details.values()) / total_weight if total_weight > 0 else 0
            
            # Tính điểm tương đồng tổng hợp cho dữ liệu đa chiều
            similarity_score = (
                weights['ks_test'] * min(1.0, ks_pvalue / self.config['p_threshold']) +
                weights['correlation'] * correlation +
                weights['cer'] * normalized_cer +
                weights['shape'] * avg_shape_similarity +
                weights['trend'] * avg_trend_similarity
            )
            
            # Thông tin chi tiết
            details = {
                'ks_pvalue': ks_pvalue,
                'correlation': correlation,
                'cer': cer,
                'shape_similarity': avg_shape_similarity,
                'trend_similarity': avg_trend_similarity,
                'similarity_score': similarity_score,
                'dimensions': dimension_details,
                'dimensions_processed': dimensions_processed
            }
            
            return similarity_score, ks_pvalue, correlation, cer, details
        
        # Mã xử lý dữ liệu một chiều - giữ nguyên code cũ
        # Đảm bảo cả hai mảng có cùng kích thước trước khi so sánh
        min_len = min(len(data1), len(data2))
        data1 = data1[:min_len]
        data2 = data2[:min_len]
        
        # Tính P-value từ KS test (Kolmogorov-Smirnov test) - kiểm tra sự giống nhau về phân phối xác suất
        _, ks_pvalue = stats.ks_2samp(data1, data2)
        
        # Tính hệ số tương quan Pearson - đo mức độ tương quan tuyến tính
        correlation = self.calculate_correlation(data1, data2)
        
        # Tính CER - đo sai số tương đối
        cer = self.calculate_cer(data1, data2)
        normalized_cer = 1.0 - min(1.0, cer / self.config['max_acceptable_cer'])
        
        # Cải tiến: Thêm so sánh theo mẫu hình dạng (pattern shape) 
        # Chuẩn hóa dữ liệu để so sánh hình dạng
        data1_norm = (np.array(data1) - np.mean(data1)) / (np.std(data1) if np.std(data1) > 0 else 1)
        data2_norm = (np.array(data2) - np.mean(data2)) / (np.std(data2) if np.std(data2) > 0 else 1)
        
        # Độ lệch trung bình giữa hai đường chuẩn hóa
        shape_diff = np.mean(np.abs(data1_norm - data2_norm))
        shape_similarity = max(0, 1 - min(1, shape_diff/3.0))  # Chuyển đổi sang thang điểm 0-1
        
        # Cải tiến: So sánh biến thiên (trend) theo thời gian
        # Tính gradient (đạo hàm rời rạc) để so sánh xu hướng biến thiên
        grad1 = np.diff(data1_norm)
        grad2 = np.diff(data2_norm)
        if len(grad1) > 0 and len(grad2) > 0:
            min_len = min(len(grad1), len(grad2))
            grad1 = grad1[:min_len]
            grad2 = grad2[:min_len]
            
            # Đếm số lần gradient có cùng dấu (cùng chiều tăng/giảm)
            same_direction = np.sum((grad1 * grad2) > 0)
            trend_similarity = same_direction / min_len if min_len > 0 else 0
        else:
            trend_similarity = 0
        
        # Cập nhật trọng số với các phương pháp mới
        weights = {
            'ks_test': 0.15,        # Giảm trọng số KS test
            'correlation': 0.25,    # Giảm trọng số tương quan Pearson
            'cer': 0.15,            # Giảm trọng số CER
            'shape': 0.25,          # Trọng số cho độ tương đồng hình dạng
            'trend': 0.20           # Trọng số cho độ tương đồng xu hướng
        }
        
        # Ghi đè trọng số từ cấu hình nếu có
        if 'enhanced_similarity_weights' in self.config:
            weights.update(self.config['enhanced_similarity_weights'])
        
        # Tính điểm tương đồng tổng hợp (giá trị càng cao càng tương đồng)
        similarity_score = (
            weights['ks_test'] * min(1.0, ks_pvalue / self.config['p_threshold']) +
            weights['correlation'] * correlation +
            weights['cer'] * normalized_cer +
            weights['shape'] * shape_similarity +
            weights['trend'] * trend_similarity
        )
        
        # Cải tiến: Lưu thêm thông tin về các thành phần tương đồng để phân tích
        details = {
            'ks_pvalue': ks_pvalue,
            'correlation': correlation,
            'cer': cer,
            'shape_similarity': shape_similarity,
            'trend_similarity': trend_similarity,
            'similarity_score': similarity_score
        }
        
        return similarity_score, ks_pvalue, correlation, cer, details
    
    def is_similar(self, data1, data2):
        """
        Kiểm tra tính tương đồng giữa hai mảng dữ liệu một chiều

        Args:
            data1, data2: Hai mảng numpy một chiều cần so sánh
            
        Returns:
            tuple: (is_similar, similarity_score, details)
        """
        if len(data1) < self.config['min_values'] or len(data2) < self.config['min_values']:
            return False, 0.0, {}
        
        # Tính điểm tương đồng và các chỉ số
        similarity_score = self.calculate_similarity(data1, data2)
        
        # Tính các chỉ số bổ sung
        correlation = np.corrcoef(data1, data2)[0, 1]
        if np.isnan(correlation):
            correlation = 0.0
        correlation = abs(correlation)
        
        _, ks_pvalue = stats.ks_2samp(data1, data2)
        cer = self.calculate_cer(data1, data2)
        
        # CẢI TIẾN: Phát hiện đặc điểm dạng chuỗi thời gian
        # Kiểm tra thay đổi đột biến
        has_sudden_change = False
        time_pattern_diff = 0.0

        # 1. Kiểm tra biến động đột ngột (spike detection)
        if len(data1) > 4 and len(data2) > 4:
            # Tính sự thay đổi giữa các điểm liên tiếp
            diff1 = np.abs(np.diff(data1))
            diff2 = np.abs(np.diff(data2))
            
            # Phát hiện sự thay đổi đột ngột (spike)
            # So sánh phân vị 95th của các thay đổi
            if len(diff1) > 0 and len(diff2) > 0:
                spike_threshold1 = np.percentile(diff1, 95)
                spike_threshold2 = np.percentile(diff2, 95)
                
                # Nếu một trong hai dữ liệu có spike gấp đôi spike của dữ liệu kia
                if spike_threshold1 > 2 * spike_threshold2 or spike_threshold2 > 2 * spike_threshold1:
                    has_sudden_change = True
                    time_pattern_diff += 0.3  # Tăng điểm khác biệt
        
        # 2. Kiểm tra chu kỳ mùa vụ (seasonality)
        has_different_seasonality = False
        if len(data1) >= 8 and len(data2) >= 8:
            # Phân tích tự tương quan (autocorrelation) - dấu hiệu của tính chu kỳ
            try:
                acf1 = np.correlate(data1 - np.mean(data1), data1 - np.mean(data1), mode='full')
                acf1 = acf1[len(acf1)//2:] / acf1[len(acf1)//2]  # Chuẩn hóa
                
                acf2 = np.correlate(data2 - np.mean(data2), data2 - np.mean(data2), mode='full')
                acf2 = acf2[len(acf2)//2:] / acf2[len(acf2)//2]  # Chuẩn hóa
                
                # So sánh hình dạng của hàm tự tương quan (chỉ lấy khoảng nửa đầu)
                min_len = min(len(acf1), len(acf2))
                half_len = min_len // 2
                if half_len > 2:
                    acf_diff = np.mean(np.abs(acf1[:half_len] - acf2[:half_len]))
                    # Nếu hàm tự tương quan khác biệt lớn, dấu hiệu của chu kỳ khác nhau
                    if acf_diff > 0.4:
                        has_different_seasonality = True
                        time_pattern_diff += 0.3  # Tăng điểm khác biệt
            except Exception:
                pass
        
        # Thông tin chi tiết
        details = {
            'ks_pvalue': ks_pvalue,
            'correlation': correlation,
            'cer': cer,
            'similarity_score': similarity_score,
            'has_sudden_change': has_sudden_change,
            'has_different_seasonality': has_different_seasonality,
            'time_pattern_diff': time_pattern_diff
        }
        
        # Cải tiến: Sử dụng ngưỡng động để xác định tính tương đồng
        similarity_threshold = 0.35  # Mặc định
        
        # Nếu có pattern rõ ràng (tương quan cao), yêu cầu similarity cao hơn
        if correlation > 0.8:
            similarity_threshold = 0.45
        
        # CẢI TIẾN: Áp dụng kiến thức về đặc tính chuỗi thời gian
        max_acceptable_cer = self.config['max_acceptable_cer']
        if has_sudden_change or has_different_seasonality:
            # Tăng ngưỡng tương đồng nếu phát hiện thấy khác biệt trong mô hình thời gian
            similarity_threshold += time_pattern_diff
            # Giảm ngưỡng CER chấp nhận được để nghiêm ngặt hơn
            max_acceptable_cer = self.config['max_acceptable_cer'] * 0.7
            logger.debug(f"Phát hiện các mẫu thời gian khác biệt: sudden_change={has_sudden_change}, diff_season={has_different_seasonality}")
        
        # Xác định dữ liệu có tương tự nhau không
        is_similar = (
            similarity_score > similarity_threshold and
            cer < max_acceptable_cer
        )
        
        if is_similar:
            self.similarity_scores.append(similarity_score)
            logger.debug(f"Dữ liệu tương tự: score={similarity_score:.4f}, KS={ks_pvalue:.4f}, corr={correlation:.4f}, CER={cer:.4f}")
        
        return is_similar, similarity_score, details
    
    def find_matching_template(self, data):
        """
        Tìm template khớp với dữ liệu một chiều
        
        Args:
            data: Mảng numpy một chiều chứa dữ liệu cần tìm template
            
        Returns:
            tuple: (template_id, similarity_score, is_match) nếu tìm thấy, hoặc (None, 0, False)
        """
        best_template_id = None
        best_cer = float('inf')
        best_similarity = -1.0
        
        # Tính các đặc trưng cơ bản của dữ liệu mới
        data_mean = np.mean(data)
        data_std = np.std(data)
        data_min = np.min(data)
        data_max = np.max(data)
        data_range = data_max - data_min
        
        # Phát hiện xu hướng trong dữ liệu gần đây
        has_trend, trend_type, trend_strength = self.detect_trend(data)
        
        # CẢI TIẾN: Phát hiện dữ liệu khác biệt lớn (outliers)
        # Tính mức dao động và sự biến đổi trong dữ liệu
        fluctuation_level = np.std(np.diff(data)) if len(data) > 1 else 0
        normalized_fluctuation = fluctuation_level / data_std if data_std > 0 else 0
        
        # Kiểm tra mức độ biến đổi đột ngột, sử dụng z-score để tìm điểm dữ liệu bất thường
        has_high_fluctuation = False
        outlier_percentage = 0
        if len(data) > 3:
            # Tính z-score cho dữ liệu
            z_scores = np.abs((data - data_mean) / data_std) if data_std > 0 else np.zeros_like(data)
            # Đếm số điểm dữ liệu có z-score > 3 (outliers tiêu chuẩn)
            outlier_count = np.sum(z_scores > 3)
            outlier_percentage = outlier_count / len(data)
            has_high_fluctuation = outlier_percentage > 0.1  # Nếu > 10% điểm dữ liệu là outliers
            
            if has_high_fluctuation:
                logger.debug(f"Phát hiện dữ liệu có biến đổi mạnh: {outlier_percentage:.2f} điểm outliers, normalized_fluctuation={normalized_fluctuation:.3f}")
        
        # CẢI TIẾN: Tạo danh sách ứng viên gộp với các template đã từng có kết quả khớp tốt trước đây
        # Bao gồm cả những template từng hoạt động tốt trong quá khứ
        potential_matches = []
        high_potential_templates = []
        
        # CẢI TIẾN: Tối ưu hóa tìm kiếm template bằng cách ưu tiên các template có lịch sử hoạt động tốt
        # Lấy ra các template được sử dụng gần đây và thường xuyên nhất (top 20%)
        frequently_used_templates = []
        if self.template_usage:
            sorted_templates = sorted(self.template_usage.items(), key=lambda x: x[1], reverse=True)
            top_n = max(3, int(len(sorted_templates) * 0.2))  # Lấy top 20% template thường dùng hoặc ít nhất 3 template
            frequently_used_templates = [tid for tid, _ in sorted_templates[:top_n]]
            
        # Điều chỉnh chiến lược khi phát hiện xu hướng hoặc biến đổi mạnh
        similarity_boost = 0.0
        cer_threshold_adjustment = 0.0
        
        if has_trend and trend_strength > 0.8:  # CẢI TIẾN: Giảm ngưỡng phát hiện xu hướng xuống 0.8 (từ 0.85)
            logger.debug(f"Đã phát hiện xu hướng mạnh: {trend_type}, độ mạnh: {trend_strength:.2f}")
            similarity_boost = 0.1  # Giảm xuống 0.1 (từ 0.15) để tăng khả năng khớp mẫu
        
        # CẢI TIẾN: Điều chỉnh cho dữ liệu biến đổi đột ngột - giảm mức độ nghiêm ngặt
        if has_high_fluctuation:
            # Khi có biến đổi mạnh, cần điều chỉnh ngưỡng CER
            cer_threshold_adjustment = -0.03  # Giảm xuống -0.03 (từ -0.05) để dễ dàng khớp mẫu hơn
            # Yêu cầu điểm tương đồng đủ cao
            similarity_boost = max(0.15, similarity_boost)  # Giảm xuống 0.15 (từ 0.2)
            
        # CẢI TIẾN: Thêm cơ chế kiểm tra nhanh với các template thường dùng
        for template_id in frequently_used_templates:
            if template_id not in self.templates:
                continue
                
            template_values = np.array(self.templates[template_id]['values'])
            
            # Tính CER trước để kiểm tra nhanh
            cer = self.calculate_cer(data, template_values)
            
            # Tạo một ngưỡng CER mở rộng cho template thường dùng
            extended_max_cer = self.config['max_acceptable_cer'] * 1.2
            
            # Nếu CER chấp nhận được, thêm vào danh sách tiềm năng
            if cer < extended_max_cer:
                high_potential_templates.append(template_id)
                
        # Kiểm tra tất cả các template
        for template_id, template in self.templates.items():
            template_values = np.array(template['values'])
            
            # CẢI TIẾN: Kiểm tra chi tiết hơn các đặc tính thống kê
            template_mean = np.mean(template_values)
            template_std = np.std(template_values)
            template_min = np.min(template_values)
            template_max = np.max(template_values)
            template_range = template_max - template_min
            
            # CẢI TIẾN: Ưu tiên các template thường xuyên sử dụng bằng cách bỏ qua kiểm tra đặc trưng 
            if template_id in high_potential_templates:
                # Với các template tiềm năng cao, bỏ qua bước lọc sơ bộ
                pass
            else:
                # CẢI TIẾN: Nới lỏng tiêu chuẩn lọc bước đầu để tăng khả năng tái sử dụng template
                # Bỏ qua các template có đặc trưng quá khác biệt
                if (abs(data_mean - template_mean) > 0.5 * data_std and  # Tăng từ 0.4 lên 0.5
                    abs(data_range - template_range) > 0.5 * data_range):  # Tăng từ 0.4 lên 0.5
                    continue
                
                # Khi có biến đổi mạnh, bổ sung kiểm tra độ lệch chuẩn - nhưng nới lỏng tiêu chí
                if has_high_fluctuation and abs(data_std - template_std) > 0.6 * template_std:  # Tăng từ 0.5 lên 0.6
                    logger.debug(f"Bỏ qua template {template_id} do khác biệt lớn về độ lệch chuẩn: {data_std:.3f} vs {template_std:.3f}")
                    continue
            
            # Cập nhật metrics của template (mark as checked, not used yet)
            self.update_template_metrics(template_id, used=False)
            
            # Tính CER trước để kiểm tra nhanh
            cer = self.calculate_cer(data, template_values)
            
            # CẢI TIẾN: Áp dụng ngưỡng CER động dựa trên phát hiện biến đổi
            # Tăng khả năng sử dụng lại template bằng cách nới lỏng ngưỡng CER
            adjusted_max_cer = self.config['max_acceptable_cer'] + cer_threshold_adjustment
            
            # CẢI TIẾN: Điều chỉnh ngưỡng CER dựa trên số lần sử dụng template
            usage_count = self.template_usage.get(template_id, 0)
            if usage_count > 3:
                # Template đã được sử dụng nhiều lần, cho phép độ linh hoạt cao hơn
                usage_bonus = min(0.03, 0.01 * (usage_count / 2))  # Tối đa +0.03 cho template dùng nhiều
                adjusted_max_cer += usage_bonus
                
            # Nếu CER quá cao, bỏ qua template này ngay
            if cer > adjusted_max_cer:
                continue
                
            # Tính điểm tương đồng nếu CER chấp nhận được
            similarity_score = self.calculate_similarity(data, template_values)
                
            # CẢI TIẾN: Điều chỉnh điểm tương đồng thông minh hơn
            adjusted_similarity = similarity_score
            
            # Áp dụng mức giảm điểm khi có xu hướng mạnh hoặc biến đổi cao
            if similarity_boost > 0:
                adjusted_similarity = similarity_score - similarity_boost
            
            # CẢI TIẾN: Tăng điểm cho template được dùng thường xuyên và gần đây
            if template_id in frequently_used_templates:
                template_age = self.blocks_processed - self.template_creation_time.get(template_id, 0)
                recency_bonus = min(0.05, 0.2 / max(1, template_age/50))  # Tăng điểm cho template gần đây, tối đa 0.05
                adjusted_similarity += recency_bonus
                
            # CẢI TIẾN: Giảm ngưỡng tương đồng tối thiểu để cân nhắc template
            if adjusted_similarity > 0.25:  # Giảm từ 0.3 xuống 0.25
                # Thêm nhiều thông tin hơn vào potential_matches để đánh giá phù hợp hơn
                potential_matches.append((template_id, cer, similarity_score, adjusted_similarity, usage_count))
        
        # CẢI TIẾN: Thử khôi phục và đánh giá một số template đã gộp/loại bỏ trước đây
        # nếu không tìm thấy template phù hợp từ danh sách hiện tại
        if not potential_matches and self.merged_templates:
            # Chỉ thử với tối đa 5 template gần đây nhất
            merged_ids = sorted(self.merged_templates.keys(), 
                              key=lambda x: self.merged_templates[x].get('last_used', 0) 
                              if isinstance(self.merged_templates[x], dict) else 0, 
                              reverse=True)[:5]
            
            for merged_id in merged_ids:
                merged_info = self.merged_templates[merged_id]
                if isinstance(merged_info, dict) and 'data' in merged_info:
                    try:
                        template_data = merged_info['data']
                        if 'values' in template_data:
                            template_values = np.array(template_data['values'])
                            cer = self.calculate_cer(data, template_values)
                            # Ngưỡng CER cao hơn một chút cho template đã gộp
                            if cer < self.config['max_acceptable_cer'] * 1.2:
                                similarity_score = self.calculate_similarity(data, template_values)
                                if similarity_score > 0.5:  # Yêu cầu điểm cao hơn cho template đã loại bỏ
                                    logger.info(f"Tìm thấy template đã loại bỏ phù hợp: {merged_id}, " +
                                              f"CER: {cer:.4f}, Tương đồng: {similarity_score:.2f}")
                                    # Khôi phục template này vào danh sách chính với ID mới
                                    new_id = self.template_counter + 1
                                    self.template_counter += 1
                                    self.templates[new_id] = template_data.copy()
                                    self.templates[new_id]['id'] = new_id
                                    self.template_usage[new_id] = merged_info.get('usage', 1)
                                    self.template_last_used[new_id] = self.blocks_processed
                                    self.template_creation_time[new_id] = self.blocks_processed - 5  # Giả định tạo gần đây
                                    # Thêm vào danh sách ứng viên
                                    potential_matches.append((new_id, cer, similarity_score, similarity_score, 1))
                                    logger.info(f"Đã khôi phục template {merged_id} thành template mới: {new_id}")
                    except Exception as e:
                        logger.warning(f"Lỗi khi kiểm tra template đã gộp {merged_id}: {str(e)}")
        
        # CẢI TIẾN: Sắp xếp thông minh hơn dựa trên nhiều tiêu chí
        if potential_matches:
            # Sắp xếp theo điểm tổng hợp: điểm tương đồng điều chỉnh * 0.7 + (1-CER) * 0.3 + bonus từ số lần sử dụng
            potential_matches.sort(
                key=lambda x: (
                    x[3] * 0.7 +  # adjusted_similarity 
                    (1-x[1]) * 0.3 +  # 1-CER
                    min(0.05, 0.01 * min(5, x[4]))  # usage bonus, tối đa 0.05
                ), 
                reverse=True
            )
            
            # Lấy template tốt nhất
            best_match = potential_matches[0]
            best_template_id, best_cer, best_similarity = best_match[0], best_match[1], best_match[2]
            
            # CẢI TIẾN: Điều chỉnh các tiêu chí loại bỏ template tốt nhất
            # Nâng cao khả năng tái sử dụng template bằng cách giảm mức độ nghiêm ngặt
            
            # Kiểm tra với dữ liệu biến đổi mạnh
            if has_high_fluctuation:
                # Nếu có biến đổi mạnh và CER vẫn tương đối cao, xem xét bỏ qua template
                adjusted_max_cer = self.config['max_acceptable_cer'] * 0.75  # Tăng từ 0.7 lên 0.75
                if best_cer > adjusted_max_cer:
                    logger.debug(f"Bỏ qua template tốt nhất (ID: {best_template_id}, CER: {best_cer:.4f}) " + 
                               f"do CER cao trong dữ liệu biến đổi mạnh (ngưỡng: {adjusted_max_cer:.4f})")
                    return None, 0, False
                
                # Đối với dữ liệu biến đổi mạnh, giảm ngưỡng điểm tương đồng
                if best_similarity < 0.65:  # Giảm từ 0.7 xuống 0.65
                    logger.debug(f"Bỏ qua template tốt nhất (ID: {best_template_id}, score: {best_similarity:.2f}) " +
                               f"do điểm tương đồng không đủ cao cho dữ liệu biến đổi mạnh")
                    return None, 0, False
                
                logger.debug(f"Chấp nhận template {best_template_id} cho dữ liệu biến đổi mạnh " + 
                           f"(CER: {best_cer:.4f}, Tương đồng: {best_similarity:.2f})")

            # Xử lý khi có xu hướng mạnh 
            elif has_trend and trend_strength > 0.92:  # Tăng từ 0.9 lên 0.92 để ít loại bỏ hơn
                if best_similarity < 0.65:  # Giảm từ 0.7 xuống 0.65
                    logger.debug(f"Bỏ qua template tốt nhất (ID: {best_template_id}, score: {best_similarity:.2f}) " + 
                               f"do xu hướng quá mạnh: {trend_type}")
                    return None, 0, False

            # Nếu quyết định sử dụng template này, cập nhật metrics
            self.update_template_metrics(best_template_id, used=True)
            
            # Lưu giá trị CER để theo dõi
            self.cer_values.append(best_cer)
            
            # Lưu điểm tương đồng
            if best_similarity > 0:
                self.similarity_scores.append(best_similarity)
                
            return best_template_id, best_similarity, True
        
        # Không tìm thấy template phù hợp
        return None, 0, False
        
    def create_template(self, data):
        """
        Tạo một template mới từ một block dữ liệu
        
        Args:
            data: Dữ liệu để tạo template (mảng 1D hoặc dictionary)
            
        Returns:
            int: ID của template mới tạo
        """
        # CẢI TIẾN: Kiểm tra kỹ lưỡng hơn khả năng tái sử dụng template đã gộp/loại bỏ
        if self.merged_templates and len(self.templates) > self.config['max_templates'] * 0.7:  # Giảm ngưỡng từ 0.8 xuống 0.7
            best_match_id = None
            best_similarity = 0
            
            # CẢI TIẾN: Tăng số lượng template được kiểm tra
            # Lấy danh sách các template đã gộp được sử dụng nhiều nhất
            merged_candidates = []
            for template_id, template_info in self.merged_templates.items():
                if isinstance(template_info, dict) and 'data' in template_info:
                    usage = template_info.get('usage', 0)
                    last_used = template_info.get('last_used', 0)
                    recency_score = max(0, 1 - ((self.blocks_processed - last_used) / max(1, self.blocks_processed)))
                    importance = template_info.get('importance', 0)
                    
                    # Tính điểm ưu tiên dựa trên tần suất sử dụng và độ gần đây
                    priority_score = (0.5 * usage / max(1, self.blocks_processed) + 
                                     0.3 * recency_score + 
                                     0.2 * importance)
                    
                    merged_candidates.append((template_id, priority_score))
            
            # Sắp xếp theo điểm ưu tiên và lấy ra top 10 template tiềm năng
            merged_candidates.sort(key=lambda x: x[1], reverse=True)
            top_candidates = [tid for tid, _ in merged_candidates[:10]]  # Tăng số lượng template kiểm tra
            
            # CẢI TIẾN: Giảm ngưỡng tương đồng để dễ dàng tái sử dụng template hơn
            min_similarity_threshold = 0.85  # Giảm từ 0.9 xuống 0.85
            
            # Kiểm tra với các template đã gộp ưu tiên
            for template_id in top_candidates:
                template_info = self.merged_templates[template_id]
                if 'data' in template_info:
                    try:
                        template_data = template_info['data']
                        if isinstance(template_data, dict) and 'values' in template_data:
                            template_values = template_data['values']
                        else:
                            template_values = template_data
                            
                        similarity = self.calculate_similarity_score(data, template_values)
                        
                        if similarity > min_similarity_threshold and similarity > best_similarity:
                            best_similarity = similarity
                            best_match_id = template_id
                            
                            # CẢI TIẾN: Nếu tìm thấy template rất phù hợp (>95%), dừng tìm kiếm ngay
                            if similarity > 0.95:
                                logger.debug(f"Tìm thấy template đã gộp rất phù hợp: {template_id}, similarity: {similarity:.3f}")
                                break
                    except Exception as e:
                        logger.warning(f"Lỗi khi tính toán tương đồng với template đã gộp {template_id}: {str(e)}")
            
            # Nếu tìm thấy template phù hợp, khôi phục nó
            if best_match_id:
                # Tạo lại template với ID mới
                template_id = self.template_counter + 1
                self.template_counter += 1
                
                template_info = self.merged_templates[best_match_id]
                
                # Lưu template (hỗ trợ cả array và dictionary)
                if isinstance(template_info['data'], dict):
                    if 'values' in template_info['data']:
                        # Template dạng đơn giản với trường values
                        self.templates[template_id] = {
                            'id': template_id,
                            'values': template_info['data']['values'].copy() if hasattr(template_info['data']['values'], 'copy') else template_info['data']['values'],
                            'use_count': 0,
                            'created_at': self.blocks_processed
                        }
                    else:
                        # Tạo bản sao sâu của dictionary
                        template_data = {}
                        for dim, values in template_info['data'].items():
                            template_data[dim] = values.copy() if hasattr(values, 'copy') else values
                        self.templates[template_id] = template_data
                else:
                    # Array (numpy array hoặc list)
                    self.templates[template_id] = {
                        'id': template_id,
                        'values': template_info['data'].copy() if hasattr(template_info['data'], 'copy') else template_info['data'],
                        'use_count': 0,
                        'created_at': self.blocks_processed
                    }
                
                # CẢI TIẾN: Khôi phục một phần thống kê sử dụng với điểm ban đầu cao hơn
                # để tăng khả năng giữ lại template này lâu hơn
                initial_usage = max(1, template_info.get('usage', 0) // 2)  # Chia đôi số lần sử dụng trước đây, tối thiểu là 1
                self.template_usage[template_id] = initial_usage
                self.template_creation_time[template_id] = self.blocks_processed
                self.template_last_used[template_id] = self.blocks_processed
                
                # CẢI TIẾN: Cập nhật trạng thái quan trọng
                importance = template_info.get('importance', 0.5)
                self.template_importance[template_id] = importance
                
                # Xóa template đã gộp khỏi danh sách nếu đã tái sử dụng thành công
                if best_similarity > 0.9:  # Chỉ xóa khi khớp rất tốt
                    del self.merged_templates[best_match_id]
                
                logger.info(f"Đã khôi phục template {best_match_id} (tương đồng: {best_similarity:.2f}) với ID mới: {template_id}")
                return template_id
        
        # CẢI TIẾN: Chủ động dọn dẹp khi số lượng template đạt ngưỡng thấp hơn
        # để có không gian cho template mới và tránh tình trạng phải xóa template hữu ích
        if len(self.templates) >= self.config['max_templates'] * 0.9:  # Giảm từ 0.95 xuống 0.9
            self.clean_expired_templates()
        
        # Tạo ID mới cho template
        template_id = self.template_counter + 1
        self.template_counter += 1
        
        # Lưu template (hỗ trợ cả array và dictionary)
        if isinstance(data, dict):
            # Tạo bản sao sâu của dictionary
            template_data = {}
            for dim, values in data.items():
                template_data[dim] = values.copy() if hasattr(values, 'copy') else values
            self.templates[template_id] = template_data
        else:
            # Array - chuẩn hóa định dạng template
            self.templates[template_id] = {
                'id': template_id,
                'values': data.copy() if hasattr(data, 'copy') else data,
                'use_count': 0,
                'created_at': self.blocks_processed
            }
        
        # Cập nhật metrics cho template mới
        self.update_template_metrics(template_id, used=True)
        
        # CẢI TIẾN: Kiểm tra nếu đã đạt số lượng template tối đa
        # và thực hiện loại bỏ thông minh hơn dựa trên nhiều tiêu chí
        if len(self.templates) > self.config['max_templates']:
            # Tính toán tầm quan trọng của template
            self.calculate_template_importance()
            
            # CẢI TIẾN: Xác định template ít quan trọng nhất dựa trên nhiều tiêu chí
            # Tạo một danh sách các template với điểm đánh giá tổng hợp
            template_scores = []
            current_block = self.blocks_processed
            
            for tid in self.templates:
                # Bỏ qua template vừa tạo
                if tid == template_id:
                    continue
                    
                # Tính các thành phần điểm
                importance = self.template_importance.get(tid, 0)
                usage = self.template_usage.get(tid, 0)
                age = current_block - self.template_creation_time.get(tid, 0)
                unused_time = current_block - self.template_last_used.get(tid, 0)
                
                # Tính điểm bảo vệ cho template
                # Template càng quan trọng, càng được dùng nhiều, càng mới thì càng ít bị xóa
                protection_score = (
                    0.4 * importance +
                    0.3 * min(1.0, usage / 10) +  # chuẩn hóa số lần sử dụng
                    0.2 * max(0, 1.0 - age / max(1, self.config['max_template_age'])) +  # template càng mới càng tốt
                    0.1 * max(0, 1.0 - unused_time / max(1, self.config['template_expiration']))  # template càng được dùng gần đây càng tốt
                )
                
                template_scores.append((tid, protection_score))
            
            # Sắp xếp theo điểm bảo vệ tăng dần (template có điểm thấp nhất sẽ bị xóa)
            template_scores.sort(key=lambda x: x[1])
            
            if template_scores:
                least_important_id = template_scores[0][0]
                
                # CẢI TIẾN: Lưu thông tin chi tiết hơn về template bị xóa để có thể tái tạo chính xác hơn
                template_to_remove = self.templates[least_important_id]
                self.merged_templates[least_important_id] = {
                    'data': template_to_remove,
                    'usage': self.template_usage.get(least_important_id, 0),
                    'last_used': self.template_last_used.get(least_important_id, 0),
                    'creation_time': self.template_creation_time.get(least_important_id, 0),
                    'importance': self.template_importance.get(least_important_id, 0),
                    'removed_at': self.blocks_processed
                }
                
                # Xóa template khỏi danh sách chính
                del self.templates[least_important_id]
                
                # Cập nhật các chỉ số liên quan
                if least_important_id in self.template_usage:
                    del self.template_usage[least_important_id]
                if least_important_id in self.template_last_used:
                    del self.template_last_used[least_important_id]
                if least_important_id in self.template_creation_time:
                    del self.template_creation_time[least_important_id]
                if least_important_id in self.template_importance:
                    del self.template_importance[least_important_id]
                
                logger.info(f"Đã loại bỏ template ID {least_important_id} do đạt giới hạn số lượng (điểm bảo vệ: {template_scores[0][1]:.3f})")
        
        return template_id
        
    def adjust_block_size(self):
        """
        Điều chỉnh kích thước block dựa trên hiệu suất nén và xu hướng dữ liệu
        
        Returns:
            int: Kích thước block mới
        """
        # Cập nhật hit ratio liên tục
        if self.blocks_processed > 0:
            current_hit_ratio = self.template_hit_count / self.blocks_processed
            
            # Cập nhật hit ratio cửa sổ
            self.window_blocks += 1
            if len(self.encoded_stream) > 0 and self.encoded_stream[-1].get('template_id') is not None:
                self.window_hit_count += 1
                
            # Nếu đủ kích thước cửa sổ, tính toán hit ratio mới và đặt lại cửa sổ
            if self.window_blocks >= self.window_size:
                window_hit_ratio = self.window_hit_count / self.window_blocks
                self.continuous_hit_ratio.append(window_hit_ratio)
                self.window_hit_count = 0
                self.window_blocks = 0
            
            # Đảm bảo luôn có ít nhất một giá trị hit ratio
            if not self.continuous_hit_ratio:
                self.continuous_hit_ratio.append(current_hit_ratio)
        else:
            current_hit_ratio = 0.0
        
        # Lấy hit ratio cửa sổ gần nhất
        recent_hit_ratio = self.continuous_hit_ratio[-1] if self.continuous_hit_ratio else current_hit_ratio
        
        # Lấy điểm tương đồng trung bình gần đây nếu có
        recent_similarity = np.mean(self.similarity_scores[-5:]) if len(self.similarity_scores) >= 5 else 1.0
        
        # ĐÁNH GIÁ ỔN ĐỊNH: Theo dõi sự ổn định của kích thước block
        # Thêm hit ratio hiện tại vào mảng theo dõi ổn định nếu đang trong giai đoạn ổn định
        if self.in_stabilization_phase:
            self.stability_hit_ratios.append(recent_hit_ratio)
            # Giới hạn kích thước cửa sổ ổn định
            if len(self.stability_hit_ratios) > self.stability_window_size:
                self.stability_hit_ratios = self.stability_hit_ratios[-self.stability_window_size:]
        
        # Kiểm tra xem kích thước block hiện tại có ổn định hay không
        if self.stable_block_size == self.current_block_size:
            self.stable_periods += 1
            
            # Tăng điểm ổn định dần dần nếu performance tốt
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
            # Đặt lại giai đoạn ổn định nếu kích thước block thay đổi
            self.stable_block_size = self.current_block_size
            self.stable_periods = 1
            
            # Khởi tạo điểm ổn định ban đầu
            self.stability_score = 20  # Điểm ổn định khởi đầu thấp
            
            # Reset giai đoạn ổn định
            self.in_stabilization_phase = False
            self.stability_hit_ratios = []
        
        # Xác định xem đã đạt ngưỡng ổn định chưa
        if self.stable_periods >= self.stability_threshold and self.stability_score >= 50:
            self.in_stabilization_phase = True
            
            # Kiểm tra xem hiệu suất hiện tại có tốt không để duy trì ổn định
            if not self.stability_hit_ratios or np.mean(self.stability_hit_ratios) >= 0.5:
                # Hiệu suất ổn định và tốt, giữ nguyên kích thước block
                logger.debug(f"Ổn định kích thước block tại {self.current_block_size} (score: {self.stability_score})")
                
                # Với điểm ổn định cao, bỏ qua chu kỳ điều chỉnh thông thường
                if self.stability_score > 80:
                    # Tăng khoảng cách giữa các lần điều chỉnh
                    if self.blocks_processed - self.last_adjustment_block < self.min_adjustment_interval * 2:
                        return self.current_block_size
        
        # Chỉ điều chỉnh nếu đã xử lý đủ số block tối thiểu
        if not self.config['adaptive_block_size'] or self.blocks_processed < self.config['min_blocks_before_adjustment']:
            return self.current_block_size
            
        # Giảm khoảng cách tối thiểu giữa các lần điều chỉnh khi gặp thay đổi đột ngột
        min_adjustment_interval = self.min_adjustment_interval
        if (len(self.similarity_scores) >= 2 and 
            (self.similarity_scores[-1] < 0.4 or 
             self.similarity_scores[-1] - self.similarity_scores[-2] < -0.2)):
            # Giảm khoảng cách để cho phép điều chỉnh nhanh hơn khi độ tương đồng thấp hoặc giảm đột ngột
            min_adjustment_interval = max(2, int(min_adjustment_interval * 0.5))
            
        if self.blocks_processed - self.last_adjustment_block < min_adjustment_interval:
            return self.current_block_size
            
        # Phát hiện xu hướng trong dữ liệu gần đây
        has_trend = False
        trend_strength = 0.0
        trend_type = "none"
        if len(self.recent_values) >= 3:
            has_trend, trend_type, trend_strength = self.detect_trend([])  # Truyền mảng rỗng vì chỉ kiểm tra dữ liệu có sẵn
        
        # Lấy CER trung bình gần đây nếu có
        recent_cer = np.mean(self.cer_values[-5:]) if len(self.cer_values) >= 5 else 0
        
        # Lấy điểm tương đồng trung bình gần đây nếu có
        recent_similarity = np.mean(self.similarity_scores[-5:]) if len(self.similarity_scores) >= 5 else 1.0
        
        # Phát hiện thay đổi đột ngột trong độ tương đồng (5 mẫu gần nhất)
        similarity_trend = 0
        if len(self.similarity_scores) >= 5:
            recent_5_similarity = self.similarity_scores[-5:]
            similarity_trend = recent_5_similarity[-1] - recent_5_similarity[0]
        
        # Số lượng thông tin có hiệu lực đã thu thập được
        r = self.blocks_processed
        rmin = max(500, self.config['min_blocks_before_adjustment'])  # Sử dụng rmin = 500 theo tài liệu
        
        # Số lần chuyển đổi kích thước block
        k = len(self.block_size_history)
        kmax = 20
        
        # Khởi tạo các biến trước để tránh lỗi tham chiếu trước khi gán giá trị
        nbest = self.current_block_size
        nnew = nbest  # Khởi tạo mặc định cho nnew
        new_block_size = nbest  # Khởi tạo giá trị mặc định cho new_block_size
        adjustment_reason = "stable_performance"  # Khởi tạo mặc định
        polynomial_adjustment = False
        hit_ratio_trend = 0
        
        # Phân tích xu hướng hit ratio để quyết định điều chỉnh
        if len(self.continuous_hit_ratio) >= 3:
            hit_ratio_trend = (self.continuous_hit_ratio[-1] - self.continuous_hit_ratio[-3])
        
        # Tính toán ρmin dựa trên mô hình Bernoulli
        if r >= rmin:
            # Tính p_min từ hit ratio hiện tại
            p_min = max(0.1, current_hit_ratio - 0.1)  # Đảm bảo p_min không quá thấp
            
            # Tính ρmin theo công thức từ tài liệu
            n = self.current_block_size
            rho_min = (8 * n) / (1 + 8 * n - 8 * n * p_min)
            
            # Lưu ρmin để theo dõi
            if not hasattr(self, 'rho_min_history'):
                self.rho_min_history = []
            self.rho_min_history.append(rho_min)
            
            # Giới hạn kích thước lịch sử
            if len(self.rho_min_history) > 10:
                self.rho_min_history = self.rho_min_history[-10:]
                
            # Lưu thông tin về ρmin vào previous_adjustments
            if len(self.previous_adjustments) > 0:
                self.previous_adjustments[-1] = (self.previous_adjustments[-1][0], 
                                               self.previous_adjustments[-1][1], 
                                               rho_min)
        
        # Kiểm tra điều kiện cho phép điều chỉnh
        if r >= rmin and k < kmax:
            # Thu thập dữ liệu cho mô hình đa thức nếu có đủ lịch sử
            if len(self.previous_adjustments) >= 3:
                try:
                    # Trích xuất dữ liệu từ lịch sử điều chỉnh trước đó
                    block_sizes = [adj[0] for adj in self.previous_adjustments]
                    hitrates = [adj[1] for adj in self.previous_adjustments]
                    
                    # Kiểm tra đủ dữ liệu và đa dạng để tạo mô hình
                    if len(set(block_sizes)) >= 3:  # Đảm bảo có ít nhất 3 kích thước khối khác nhau
                        # Tạo mô hình đa thức bậc 2 để tối ưu hóa kích thước khối
                        coeffs = np.polyfit(block_sizes, hitrates, 2)
                        a2, a1, a0 = coeffs
                        
                        # Tìm kích thước khối tối ưu dựa trên đa thức (đỉnh của parabol)
                        # f'(n) = 2*a2*n + a1 = 0 => n = -a1 / (2*a2)
                        if a2 < 0:  # Đảm bảo tìm được giá trị cực đại
                            optimal_size = int(-a1 / (2 * a2))
                            
                            # Kiểm tra xem giá trị tối ưu có nằm trong khoảng hợp lý
                            min_size = self.config['min_block_size']
                            max_size = self.config['max_block_size']
                            
                            if min_size <= optimal_size <= max_size:
                                polynomial_adjustment = True
                                nnew = optimal_size
                                adjustment_reason = "polynomial_optimization"
                                
                                # Tránh điều chỉnh quá lớn trong một lần
                                max_change = int(nbest * 0.15)  # Tối đa thay đổi 15% trong một lần
                                if abs(nnew - nbest) > max_change:
                                    if nnew > nbest:
                                        nnew = nbest + max_change
                                    else:
                                        nnew = max(nbest - max_change, int(nbest * 0.85))  # Giới hạn giảm xuống tối đa 15%
                except Exception as e:
                    # Ghi log lỗi để debug
                    logger.warning(f"Lỗi khi tạo mô hình đa thức: {str(e)}")
                    polynomial_adjustment = False
            
            # Nếu không thể sử dụng mô hình đa thức, sử dụng thuật toán thay thế
            if not polynomial_adjustment:
                # Kết hợp nhiều yếu tố để quyết định điều chỉnh
                # 1. Hit ratio hiện tại và xu hướng
                # 2. Độ tương đồng gần đây
                # 3. Xu hướng dữ liệu
                
                # Tính trọng số tổng hợp cho việc tăng/giảm kích thước
                hr_weight = 0.4     # Giảm trọng số cho hit ratio
                sim_weight = 0.5    # Tăng trọng số cho độ tương đồng
                trend_weight = 0.1  # Trọng số cho xu hướng dữ liệu
                
                # Điều chỉnh trọng số khi đang trong giai đoạn ổn định
                stability_reduction = 0.0
                if self.in_stabilization_phase:
                    # Tính hệ số giảm dựa trên điểm ổn định
                    stability_reduction = min(0.8, self.stability_score / 100)
                    
                    # Giảm các trọng số khi ổn định
                    hr_weight *= (1.0 - stability_reduction * 0.5)
                    sim_weight *= (1.0 - stability_reduction * 0.3)
                
                # Tính điểm cho việc tăng kích thước
                increase_score = 0
                
                # Hit ratio cao và không giảm -> tăng điểm
                if recent_hit_ratio > 0.6:
                    increase_score += 0.5 * hr_weight
                if hit_ratio_trend >= 0:
                    increase_score += 0.5 * hr_weight
                
                # Độ tương đồng cao -> tăng điểm
                if recent_similarity > 0.7:
                    increase_score += sim_weight
                
                # Dữ liệu ổn định (không có xu hướng mạnh) -> tăng điểm
                if not has_trend or trend_strength < 0.5:
                    increase_score += trend_weight
                
                # Ngược lại, tính điểm cho việc giảm kích thước
                decrease_score = 0
                
                # Hit ratio thấp hoặc đang giảm -> tăng điểm giảm
                if recent_hit_ratio < 0.5:
                    decrease_score += 0.5 * hr_weight
                if hit_ratio_trend < 0:
                    decrease_score += 0.5 * hr_weight
                
                # Độ tương đồng thấp hoặc giảm đột ngột -> tăng điểm giảm mạnh
                if recent_similarity < 0.6:
                    decrease_score += sim_weight
                # Xu hướng giảm độ tương đồng -> tăng điểm giảm
                if similarity_trend < -0.1:
                    decrease_score += 0.5 * sim_weight  # Thêm điểm nếu độ tương đồng đang giảm
                
                # Dữ liệu có xu hướng mạnh -> tăng điểm giảm (để bắt kịp thay đổi)
                if has_trend and trend_strength > 0.5:
                    decrease_score += trend_weight
                
                # Áp dụng hệ số giảm cho các điểm khi ổn định
                adjustment_damper = 1.0
                if self.in_stabilization_phase:
                    adjustment_damper = 1.0 - stability_reduction
                    
                    # Kiểm tra nếu hiệu suất suy giảm đáng kể
                    if len(self.stability_hit_ratios) >= 3:
                        current_stable_hr = np.mean(self.stability_hit_ratios[-3:])
                        if current_stable_hr < 0.4 and recent_similarity < 0.5:
                            # Hiệu suất kém, thoát khỏi giai đoạn ổn định
                            logger.info(f"Thoát khỏi giai đoạn ổn định do hiệu suất kém (HR: {current_stable_hr:.2f}, Sim: {recent_similarity:.2f})")
                            self.in_stabilization_phase = False
                            self.stability_score = max(0, self.stability_score - 30)
                            adjustment_damper = 1.0  # Bỏ qua hệ số giảm
                
                # Quyết định điều chỉnh dựa trên điểm số
                if increase_score > decrease_score + 0.2:  # Ưu tiên tăng từ từ
                    # Tăng chậm hơn với hệ số thấp hơn
                    adjustment_factor = min(0.15, (increase_score - decrease_score) * 0.5)
                    # Áp dụng hệ số giảm khi ổn định
                    adjustment_factor *= adjustment_damper
                    
                    # CẢI TIẾN: Giới hạn tăng dần theo kích thước hiện tại
                    if nbest > 100:
                        # Giảm mức tăng đối với các khối lớn
                        adjustment_factor = min(adjustment_factor, 0.08)
                    elif nbest > 50:
                        # Giảm mức tăng đối với các khối trung bình
                        adjustment_factor = min(adjustment_factor, 0.12)
                    
                    # CẢI TIẾN: Giới hạn mức tăng tuyệt đối trong một lần
                    max_absolute_increase = 10  # Tăng tối đa 10 đơn vị trong một lần
                    
                    # Tính toán kích thước mới và áp dụng giới hạn
                    raw_new_size = int(nbest * (1 + adjustment_factor))
                    capped_new_size = min(raw_new_size, nbest + max_absolute_increase)
                    
                    # Thêm log chi tiết cho việc tăng kích thước
                    if raw_new_size != capped_new_size:
                        logger.debug(f"Giới hạn tăng kích thước: {raw_new_size} -> {capped_new_size} (giới hạn tăng tối đa: {max_absolute_increase})")
                    
                    nnew = capped_new_size
                    adjustment_reason = f"gradual_increase_by_weighted_score{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                elif decrease_score > increase_score + 0.1:  # Ưu tiên giảm nhanh
                    # Tính độ giảm dựa trên mức điểm và cả giá trị hiện tại của kích thước block
                    # Mức giảm được điều chỉnh để giảm dần theo các bước, tránh giảm đột ngột
                    
                    # Giảm mức độ điều chỉnh tối đa khi kích thước block lớn
                    if nbest > 50:
                        # Giảm nhiều hơn khi kích thước lớn nhưng giảm dần dần
                        adjustment_factor = min(0.2, (decrease_score - increase_score) * 0.4)
                        # Áp dụng hệ số giảm khi ổn định
                        adjustment_factor *= adjustment_damper
                        
                        nnew = int(nbest * (1 - adjustment_factor))
                        adjustment_reason = f"gradual_decrease_from_large_size{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                    elif nbest > 30:
                        # Giảm ít hơn ở kích thước trung bình
                        adjustment_factor = min(0.15, (decrease_score - increase_score) * 0.3)
                        # Áp dụng hệ số giảm khi ổn định
                        adjustment_factor *= adjustment_damper
                        
                        nnew = int(nbest * (1 - adjustment_factor))
                        adjustment_reason = f"moderate_decrease_from_medium_size{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                    else:
                        # Giảm rất ít ở kích thước nhỏ
                        adjustment_factor = min(0.1, (decrease_score - increase_score) * 0.2)
                        # Áp dụng hệ số giảm khi ổn định
                        adjustment_factor *= adjustment_damper
                        
                        nnew = int(nbest * (1 - adjustment_factor))
                        adjustment_reason = f"gentle_decrease_from_small_size{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                else:
                    # Điểm số gần nhau -> điều chỉnh dựa trên xu hướng với mức tăng cao hơn
                    if hit_ratio_trend > 0.05 or similarity_trend > 0:  # Giảm ngưỡng phát hiện xu hướng tốt
                        # CẢI TIẾN: Giảm mức tăng khi có xu hướng tích cực
                        adjustment_factor = 0.15  # Giảm từ 25% xuống 15%
                        # Áp dụng hệ số giảm khi ổn định
                        adjustment_factor *= adjustment_damper
                        
                        # CẢI TIẾN: Giới hạn mức tăng tuyệt đối
                        max_absolute_increase = 8  # Tăng tối đa 8 đơn vị trong một lần
                        
                        # Tính toán kích thước mới và áp dụng giới hạn
                        raw_new_size = int(nbest * (1 + adjustment_factor))
                        capped_new_size = min(raw_new_size, nbest + max_absolute_increase)
                        
                        # Thêm log chi tiết cho việc tăng kích thước
                        if raw_new_size != capped_new_size:
                            logger.debug(f"Giới hạn tăng kích thước dựa trên xu hướng: {raw_new_size} -> {capped_new_size} (giới hạn tăng tối đa: {max_absolute_increase})")
                        
                        nnew = capped_new_size
                        adjustment_reason = f"moderate_increase_by_trend{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                    elif hit_ratio_trend < -0.1 or similarity_trend < -0.05:
                        # Điều chỉnh giảm theo kích thước hiện tại, giảm dần dần
                        if nbest > 50:
                            adjustment_factor = 0.1  # Giảm 10% khi kích thước lớn
                            # Áp dụng hệ số giảm khi ổn định
                            adjustment_factor *= adjustment_damper
                            
                            nnew = int(nbest * (1 - adjustment_factor))
                            adjustment_reason = f"adaptive_decrease_by_trend_large{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                        elif nbest > 30:
                            adjustment_factor = 0.07  # Giảm 7% ở kích thước trung bình
                            # Áp dụng hệ số giảm khi ổn định
                            adjustment_factor *= adjustment_damper
                            
                            nnew = int(nbest * (1 - adjustment_factor))
                            adjustment_reason = f"adaptive_decrease_by_trend_medium{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                        else:
                            adjustment_factor = 0.05  # Giảm 5% ở kích thước nhỏ
                            # Áp dụng hệ số giảm khi ổn định
                            adjustment_factor *= adjustment_damper
                            
                            nnew = int(nbest * (1 - adjustment_factor))
                            adjustment_reason = f"adaptive_decrease_by_trend_small{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                    else:
                        # Nếu các chỉ số ổn định và tương đối tốt, vẫn tăng nhẹ
                        if recent_hit_ratio > 0.5 and recent_similarity > 0.55:  # Giảm ngưỡng tương đồng
                            # CẢI TIẾN: Giảm mức tăng cho tình huống ổn định
                            adjustment_factor = 0.05  # Giảm từ 10% xuống 5%
                            # Áp dụng hệ số giảm khi ổn định
                            adjustment_factor *= adjustment_damper
                            
                            # CẢI TIẾN: Giới hạn mức tăng tuyệt đối
                            max_absolute_increase = 5  # Tăng tối đa 5 đơn vị trong một lần cho tình huống ổn định
                            
                            # Tính toán kích thước mới và áp dụng giới hạn
                            raw_new_size = int(nbest * (1 + adjustment_factor))
                            capped_new_size = min(raw_new_size, nbest + max_absolute_increase)
                            
                            # Thêm log chi tiết cho việc tăng kích thước
                            if raw_new_size != capped_new_size:
                                logger.debug(f"Giới hạn tăng nhẹ kích thước ổn định: {raw_new_size} -> {capped_new_size} (giới hạn: {max_absolute_increase})")
                            
                            nnew = capped_new_size
                            adjustment_reason = f"gentle_increase_for_stable_good_metrics{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
                        else:
                            nnew = nbest  # Giữ nguyên
                            adjustment_reason = f"stable_performance{'' if adjustment_damper == 1.0 else f'_with_stability_{int(stability_reduction*100)}'}"
        
        # Cửa sổ từ chối cập nhật (wn) - ngưỡng tối thiểu để thay đổi
        wn = max(1, int(nbest * 0.03))  # Giảm từ 5% xuống 3%, với giá trị tối thiểu là 1
        
        # Điều chỉnh cửa sổ từ chối khi ổn định (yêu cầu thay đổi lớn hơn khi đã ổn định)
        if self.in_stabilization_phase:
            stability_factor = self.stability_score / self.max_stability_score
            # Tăng ngưỡng thay đổi tối thiểu khi ổn định (từ 3% đến 8%)
            wn = max(1, int(nbest * (0.03 + 0.05 * stability_factor)))
            logger.debug(f"Tăng ngưỡng thay đổi block size từ 3% lên {(0.03 + 0.05 * stability_factor)*100:.1f}% do ổn định (score: {self.stability_score})")
        
        # Các điều kiện đặc biệt khác - giảm ngưỡng để dễ kích hoạt hơn
        special_condition = (recent_hit_ratio < 0.35 or 
                             recent_similarity < 0.45 or 
                             (recent_hit_ratio > 0.8 and recent_similarity > 0.7) or
                             (self.blocks_processed < 10))  # Thêm điều kiện đặc biệt cho giai đoạn rất sớm
        
        # Khi đã ổn định, đặt lại định nghĩa của điều kiện đặc biệt để hạn chế điều chỉnh không cần thiết
        if self.in_stabilization_phase and self.stability_score > 50:
            # Điều chỉnh các điều kiện đặc biệt tùy theo mức độ ổn định
            # Chỉ kích hoạt khi hiệu suất thực sự rất tệ hoặc rất tốt
            stability_factor = self.stability_score / self.max_stability_score
            hr_low_threshold = 0.35 - (0.15 * stability_factor)  # Giảm từ 0.35 xuống tối thiểu 0.2
            hr_high_threshold = 0.8 + (0.1 * stability_factor)   # Tăng từ 0.8 lên tối đa 0.9
            sim_low_threshold = 0.45 - (0.2 * stability_factor)  # Giảm từ 0.45 xuống tối thiểu 0.25
            sim_high_threshold = 0.7 + (0.15 * stability_factor) # Tăng từ 0.7 lên tối đa 0.85
            
            # Áp dụng ngưỡng mới cho điều kiện đặc biệt
            special_condition = (recent_hit_ratio < hr_low_threshold or 
                                recent_similarity < sim_low_threshold or 
                                (recent_hit_ratio > hr_high_threshold and recent_similarity > sim_high_threshold))
            
            logger.debug(f"Áp dụng điều kiện đặc biệt ổn định với ngưỡng: HR={hr_low_threshold:.2f}/{hr_high_threshold:.2f}, Sim={sim_low_threshold:.2f}/{sim_high_threshold:.2f}")
        
        # Đảm bảo nnew đã được khởi tạo và khác None
        if nnew is None:
            nnew = nbest
            logger.warning("Giá trị nnew chưa được khởi tạo, sử dụng giá trị mặc định")
        
        # Chỉ cập nhật nếu sự thay đổi đủ lớn hoặc có lý do đặc biệt
        if abs(nnew - nbest) > wn or special_condition:
            # Giới hạn tốc độ giảm kích thước block
            if nnew < nbest:
                # Kiểm tra lịch sử để đảm bảo giảm từ từ
                if len(self.block_size_history) >= 2:
                    # Lấy kích thước block từ 2 lần điều chỉnh gần nhất
                    prev_size = self.block_size_history[-1]['old_size']
                    prev_prev_size = self.block_size_history[-2]['old_size']
                    
                    # Nếu đã giảm trong lần điều chỉnh trước, giới hạn mức giảm trong lần này
                    if prev_size < prev_prev_size:
                        # Tính tỷ lệ giảm trong lần điều chỉnh trước
                        prev_decrease_ratio = prev_size / prev_prev_size
                        
                        # Giảm dần mức độ giảm theo thời gian và mức độ ổn định
                        min_decrease_ratio = 0.85  # Giảm tối đa 15% mặc định
                        if self.in_stabilization_phase:
                            # Tăng giới hạn giảm khi ổn định (giảm ít hơn)
                            stability_factor = self.stability_score / self.max_stability_score
                            min_decrease_ratio = 0.85 + (0.1 * stability_factor)  # Từ 0.85 đến 0.95
                        
                        # Lấy giá trị lớn hơn giữa tỷ lệ giảm trước đó và ngưỡng tối thiểu
                        current_min_ratio = max(prev_decrease_ratio, min_decrease_ratio)
                        
                        # Đảm bảo kích thước mới không giảm quá mức so với kích thước hiện tại
                        min_allowed_size = int(nbest * current_min_ratio)
                        if nnew < min_allowed_size:
                            logger.debug(f"Giới hạn giảm block size: từ {nnew} lên {min_allowed_size} (tỷ lệ: {current_min_ratio:.2f})")
                            nnew = min_allowed_size
                            adjustment_reason += "_with_decrease_limit"
            
            # Giới hạn trong phạm vi cho phép
            new_block_size = max(self.config['min_block_size'], 
                              min(self.config['max_block_size'], nnew))
            
            # Xử lý trường hợp đặc biệt: nếu đang ở kích thước lớn nhất và hit ratio giảm -> giảm từ từ
            if nbest == self.config['max_block_size'] and (hit_ratio_trend < 0 or similarity_trend < 0):
                # Giảm từ từ từ kích thước lớn nhất, nhưng điều chỉnh tỷ lệ giảm dựa trên mức độ ổn định
                decrease_ratio = 0.1  # Giảm 10% mặc định
                
                if self.in_stabilization_phase:
                    # Giảm ít hơn khi ổn định
                    stability_factor = self.stability_score / self.max_stability_score
                    decrease_ratio = 0.1 * (1.0 - stability_factor * 0.5)  # Giảm từ 10% xuống tối thiểu 5%
                
                new_block_size = int(nbest * (1.0 - decrease_ratio))
                adjustment_reason = f"gradual_reduce_from_max_due_to_declining_metrics{'' if not self.in_stabilization_phase else f'_with_stability_{int(self.stability_score)}'}"
            
            # Nếu đang ở kích thước nhỏ nhất và chỉ số hiệu suất tốt -> tăng mạnh hơn
            if nbest == self.config['min_block_size']:
                # Tăng nhanh hơn nếu các chỉ số tốt
                if recent_hit_ratio > 0.5 or recent_similarity > 0.6:
                    increase_ratio = 1.0  # Tăng 100% mặc định
                    
                    if self.in_stabilization_phase:
                        # Giảm mức tăng khi đã ổn định
                        stability_factor = self.stability_score / self.max_stability_score
                        increase_ratio = 1.0 * (1.0 - stability_factor * 0.3)  # Giảm từ 100% xuống tối thiểu 70%
                    
                    new_block_size = int(nbest * (1.0 + increase_ratio))
                    adjustment_reason = f"aggressive_increase_from_min_due_to_good_metrics{'' if not self.in_stabilization_phase else f'_with_stability_{int(self.stability_score)}'}"
                # Vẫn tăng nhẹ nếu xu hướng tích cực
                elif hit_ratio_trend > 0 and similarity_trend > 0:
                    increase_ratio = 0.5  # Tăng 50% mặc định
                    
                    if self.in_stabilization_phase:
                        # Giảm mức tăng khi đã ổn định
                        stability_factor = self.stability_score / self.max_stability_score
                        increase_ratio = 0.5 * (1.0 - stability_factor * 0.4)  # Giảm từ 50% xuống tối thiểu 30%
                    
                    new_block_size = int(nbest * (1.0 + increase_ratio))
                    adjustment_reason = f"stronger_increase_from_min_due_to_improving_trends{'' if not self.in_stabilization_phase else f'_with_stability_{int(self.stability_score)}'}"
                # Thêm điều kiện tăng mặc định từ mức tối thiểu
                else:
                    increase_ratio = 0.3  # Tăng 30% mặc định
                    
                    if self.in_stabilization_phase:
                        # Giảm mức tăng khi đã ổn định
                        stability_factor = self.stability_score / self.max_stability_score
                        increase_ratio = 0.3 * (1.0 - stability_factor * 0.5)  # Giảm từ 30% xuống tối thiểu 15%
                    
                    new_block_size = int(nbest * (1.0 + increase_ratio))
                    adjustment_reason = f"default_increase_from_min_size{'' if not self.in_stabilization_phase else f'_with_stability_{int(self.stability_score)}'}"
            
            # Thêm điều kiện đặc biệt cho giai đoạn đầu: ưu tiên tăng kích thước nhanh hơn nếu hiệu suất tốt
            if self.blocks_processed <= self.config['min_blocks_before_adjustment'] * 3:  # Mở rộng giai đoạn đầu
                # Tăng kích thước nhanh ở giai đoạn đầu
                if recent_similarity > 0.55:  # Giảm ngưỡng tương đồng từ 0.65 xuống 0.55
                    if new_block_size < int(nbest * 1.5):  # Chỉ áp dụng nếu sự tăng hiện tại chưa đủ lớn
                        new_block_size = int(nbest * 1.5)  # Tăng từ 30% lên 50% ở giai đoạn đầu
                        adjustment_reason = "early_stage_aggressive_increase_due_to_good_performance"
                # Thêm điều kiện tăng mặc định ở giai đoạn đầu nếu không quá tệ
                elif recent_hit_ratio > 0.3 and new_block_size < int(nbest * 1.2):
                    new_block_size = int(nbest * 1.2)  # Tăng mặc định 20% ở giai đoạn đầu
                    adjustment_reason = "early_stage_default_increase"
            
            # Kiểm tra thêm điều kiện giảm đột ngột
            # Nếu điều chỉnh mới giảm quá nhiều so với kích thước hiện tại, giới hạn mức giảm
            if new_block_size < nbest:
                # Tính tỷ lệ giảm đề xuất
                proposed_decrease_ratio = new_block_size / nbest
                
                # Điều chỉnh giới hạn giảm dựa trên mức độ ổn định
                large_block_limit = 0.7  # Giảm tối đa 30% mặc định cho block lớn
                medium_block_limit = 0.8  # Giảm tối đa 20% mặc định cho block trung bình
                small_block_limit = 0.9  # Giảm tối đa 10% mặc định cho block nhỏ
                
                if self.in_stabilization_phase:
                    # Tăng giới hạn (giảm ít hơn) khi ổn định
                    stability_factor = self.stability_score / self.max_stability_score
                    large_block_limit += 0.1 * stability_factor  # Từ 0.7 đến 0.8
                    medium_block_limit += 0.1 * stability_factor  # Từ 0.8 đến 0.9
                    small_block_limit += 0.05 * stability_factor  # Từ 0.9 đến 0.95
                
                # Áp dụng giới hạn tùy theo kích thước block
                if nbest > 50 and proposed_decrease_ratio < large_block_limit:
                    new_block_size = int(nbest * large_block_limit)
                    adjustment_reason += f"_with_large_block_decrease_limit_{int(large_block_limit*100)}"
                # Nếu kích thước block hiện tại lớn hơn 30, tỷ lệ giảm không được nhỏ hơn giới hạn
                elif nbest > 30 and proposed_decrease_ratio < medium_block_limit:
                    new_block_size = int(nbest * medium_block_limit)
                    adjustment_reason += f"_with_medium_block_decrease_limit_{int(medium_block_limit*100)}"
                # Nếu không, tỷ lệ giảm không được nhỏ hơn giới hạn block nhỏ
                elif proposed_decrease_ratio < small_block_limit:
                    new_block_size = int(nbest * small_block_limit)
                    adjustment_reason += f"_with_small_block_decrease_limit_{int(small_block_limit*100)}"
        
            # Thêm thông tin về ổn định vào lý do điều chỉnh
            if self.in_stabilization_phase:
                adjustment_reason += f"_stability_score_{self.stability_score}"
        
        # Lưu lịch sử thay đổi với thông tin chi tiết hơn
        self.block_size_history.append({
            'block_number': self.blocks_processed,
            'old_size': self.current_block_size,
            'new_size': new_block_size,
            'recent_cer': recent_cer,
            'recent_similarity': recent_similarity,
            'similarity_trend': similarity_trend,
            'has_trend': has_trend,
            'trend_type': trend_type,
            'trend_strength': trend_strength,
            'hit_ratio': current_hit_ratio,
            'window_hit_ratio': recent_hit_ratio,
            'hit_ratio_trend': hit_ratio_trend,
            'adjustment_reason': adjustment_reason
        })
        
        # Lưu thông tin chi tiết hơn trong log
        logger.info(f"Điều chỉnh kích thước block: {self.current_block_size} -> {new_block_size} "
                  f"(hit ratio: {current_hit_ratio:.2f}, window HR: {recent_hit_ratio:.2f}, "
                  f"CER: {recent_cer:.4f}, Similarity: {recent_similarity:.4f}, "
                  f"Similarity trend: {similarity_trend:.4f}, "
                  f"Lý do: {adjustment_reason})")
        
        self.current_block_size = new_block_size
        self.last_adjustment_block = self.blocks_processed
        
        # Lưu lịch sử điều chỉnh để phân tích
        self.previous_adjustments.append((new_block_size, current_hit_ratio))
        if abs(nnew - nbest) <= wn and not special_condition:
            # Nếu không có điều chỉnh, vẫn lưu thông tin vào previous_adjustments để tích lũy dữ liệu cho đa thức
            if r % 20 == 0:  # Chỉ lưu định kỳ để không làm tràn bộ nhớ
                self.previous_adjustments.append((nbest, current_hit_ratio))
        
        # Lưu lịch sử và thông báo
        if new_block_size != self.current_block_size:
            # CẢI TIẾN: Thêm kiểm tra lịch sử tăng block size
            if new_block_size > self.current_block_size:
                # Đếm số lần tăng liên tiếp trong lịch sử gần đây (3 lần điều chỉnh gần nhất)
                consecutive_increases = 0
                increase_ratio_sum = 0
                
                for i in range(min(3, len(self.block_size_history))):
                    history_entry = self.block_size_history[-1-i]
                    if history_entry['new_size'] > history_entry['old_size']:
                        consecutive_increases += 1
                        increase_ratio = history_entry['new_size'] / history_entry['old_size']
                        increase_ratio_sum += increase_ratio - 1.0  # Chỉ tính phần tăng (ví dụ: 1.2 -> 0.2)
                
                # Nếu đã tăng liên tiếp và tổng mức tăng lớn, hạn chế tăng thêm
                if consecutive_increases >= 2 and increase_ratio_sum > 0.3:  # Đã tăng > 30% trong 3 lần gần nhất
                    # Giảm mức tăng dựa trên số lần tăng liên tiếp
                    damping_factor = 0.5 - (consecutive_increases * 0.1)  # 0.5, 0.4, 0.3, ...
                    damping_factor = max(0.1, damping_factor)  # Tối thiểu vẫn tăng 10% so với mức hiện tại
                    
                    # Tính lại block size với mức tăng được điều chỉnh
                    max_increase = int(self.current_block_size * damping_factor)
                    capped_size = min(new_block_size, self.current_block_size + max_increase)
                    
                    if capped_size < new_block_size:
                        logger.info(f"Hạn chế tăng kích thước block do đã tăng {consecutive_increases} lần liên tiếp " + 
                                  f"(từ {new_block_size} xuống {capped_size}, giới hạn tăng: {damping_factor*100:.1f}%)")
                        new_block_size = capped_size
                        adjustment_reason += "_with_consecutive_increase_limit"
            
            # CẢI TIẾN: Thêm kiểm tra cho trường hợp tăng vọt
            relative_change = abs(new_block_size - self.current_block_size) / self.current_block_size
            if relative_change > 0.5:  # Nếu thay đổi >50%
                # Giới hạn thay đổi tối đa là 50%
                max_change = int(self.current_block_size * 0.5)
                if new_block_size > self.current_block_size:
                    capped_size = self.current_block_size + max_change
                else:
                    capped_size = self.current_block_size - max_change
                
                logger.warning(f"Thay đổi block size quá lớn ({relative_change*100:.1f}%), " + 
                             f"hạn chế từ {new_block_size} thành {capped_size} (giới hạn thay đổi: 50%)")
                new_block_size = capped_size
                adjustment_reason += "_with_extreme_change_limit"
                
            # Ghi nhận sự thay đổi vào lịch sử
            self.block_size_history.append({
                'block': self.blocks_processed,
                'old_size': self.current_block_size,
                'new_size': new_block_size,
                'reason': adjustment_reason
            })
            
            logger.info(f"Điều chỉnh kích thước block: {self.current_block_size} -> {new_block_size} " +
                       f"(lý do: {adjustment_reason})")
                       
            # Cập nhật thời điểm điều chỉnh cuối cùng và kích thước hiện tại
            self.last_adjustment_block = self.blocks_processed
            self.current_block_size = new_block_size
            
            # Lưu trữ thông số cho mô hình đa thức
            current_hitrate = self.continuous_hit_ratio[-1] if self.continuous_hit_ratio else 0
            self.previous_adjustments.append((new_block_size, current_hitrate, recent_similarity))
        
        return self.current_block_size
        
    def compress(self, data):
        """
        Nén dữ liệu một chiều
        
        Args:
            data: List các điểm dữ liệu, mỗi điểm có dạng {value: float, timestamp: datetime}
        """
        try:
            n = len(data)
            if n < self.config['min_values']:
                logger.warning(f"Số lượng điểm dữ liệu ({n}) quá ít để nén")
                return None

            # Chuyển dữ liệu thành mảng numpy một chiều
            values = np.array([point['value'] for point in data], dtype=float)
            timestamps = [point['timestamp'] for point in data]

            # Reset trạng thái
            self.reset()
            
            # Xử lý từng block
            current_idx = 0
            while current_idx < n:
                # Lấy block tiếp theo
                end_idx = min(current_idx + self.current_block_size, n)
                block = values[current_idx:end_idx]
                
                # Tìm template phù hợp nhất
                template_id, similarity_score, is_match = self.find_matching_template(block)
                
                if template_id is not None:
                    # Sử dụng template tìm thấy
                    self.template_hit_count += 1
                    self.window_hit_count += 1
                    self.templates_used.add(template_id)
                    self.update_template_metrics(template_id)
                    
                    # Tính CER cho template đã tìm thấy
                    template_values = np.array(self.templates[template_id]['values'])
                    cer = self.calculate_cer(block, template_values)
                    self.cer_values.append(cer)
                else:
                    # Tạo template mới
                    template_id = self.template_counter
                    self.template_counter += 1
                    self.templates[template_id] = {
                        'id': template_id,
                        'values': block.tolist(),
                        'use_count': 0,
                        'created_at': self.blocks_processed
                    }
                    similarity_score = 1.0
                    cer = 0.0

                # Thêm vào encoded stream
                self.encoded_stream.append({
                    'template_id': template_id,
                    'start_idx': current_idx,
                    'length': len(block),
                    'similarity_score': similarity_score,
                    'cer': cer
                })

                # Cập nhật các biến theo dõi
                self.blocks_processed += 1
                self.window_blocks += 1
                
                # Tính hit ratio trong cửa sổ
                if self.window_blocks >= self.window_size:
                    window_hit_ratio = self.window_hit_count / self.window_blocks
                    self.continuous_hit_ratio.append(window_hit_ratio)
                    # Lưu hit ratio theo block
                    self.hit_ratio_by_block.append((self.blocks_processed, window_hit_ratio))
                    self.window_hit_count = 0
                    self.window_blocks = 0

                # Điều chỉnh kích thước block nếu cần
                if self.config['adaptive_block_size'] and self.blocks_processed >= self.config['min_blocks_before_adjustment']:
                    self.adjust_block_size()

                # Di chuyển đến block tiếp theo
                current_idx = end_idx

            # Tính các chỉ số hiệu suất
            hit_ratio = self.template_hit_count / max(1, self.blocks_processed)
            avg_cer = np.mean(self.cer_values) if self.cer_values else 0.0
            avg_similarity = np.mean(self.similarity_scores) if self.similarity_scores else 0.0

            # Tính compression ratio
            original_size = n * 8  # 8 bytes cho mỗi giá trị float
            template_size = sum(len(template['values']) * 8 for template in self.templates.values())
            encoded_size = len(self.encoded_stream) * (4 + 4 + 4)  # template_id, start_idx, length
            compression_ratio = original_size / max(1, template_size + encoded_size)

            # Tính cost và lưu vào history
            cost = self.calculate_cost(avg_cer, compression_ratio)
            self.cost_values.append(cost)

            # Tạo kết quả với đầy đủ thông tin
            result = {
                'templates': self.templates,
                'encoded_stream': self.encoded_stream,
                'compression_ratio': compression_ratio,
                'hit_ratio': hit_ratio,
                'avg_cer': avg_cer,
                'avg_similarity': avg_similarity,
                'cost': cost,
                'block_size_history': self.block_size_history,
                'total_values': n,
                'templates_used': len(self.templates_used),
                'templates_total': len(self.templates),
                'continuous_hit_ratio': self.continuous_hit_ratio,
                'hit_ratio_by_block': self.hit_ratio_by_block
            }

            # Log thông tin chi tiết
            logger.info(f"Nén dữ liệu hoàn tất: {n} mẫu -> {len(self.templates)} templates, {self.blocks_processed} blocks")
            logger.info(f"Hit ratio: {hit_ratio:.2f}, CER: {avg_cer:.4f}, Cost: {cost:.4f}")

            return result

        except Exception as e:
            logger.error(f"Lỗi trong quá trình nén: {str(e)}")
            return None
    
    def calculate_similarity(self, block1: np.ndarray, block2: np.ndarray) -> float:
        """
        Tính độ tương đồng giữa hai block dữ liệu
        
        Args:
            block1: Block dữ liệu thứ nhất
            block2: Block dữ liệu thứ hai
        
        Returns:
            float: Điểm tương đồng từ 0 đến 1
        """
        try:
            if len(block1) != len(block2):
                return 0.0

            # Tính các thành phần tương đồng
            # 1. Tương quan Pearson
            correlation = np.corrcoef(block1, block2)[0, 1]
            if np.isnan(correlation):
                correlation = 0.0
            correlation = abs(correlation)  # Lấy giá trị tuyệt đối

            # 2. KS test
            _, ks_pvalue = stats.ks_2samp(block1, block2)
            
            # 3. Compression Error Rate (CER)
            cer = self.calculate_cer(block1, block2)
            cer_score = 1 - cer  # Chuyển CER thành điểm (cao hơn tốt hơn)

            # Tính điểm tổng hợp theo trọng số
            weights = self.config['similarity_weights']
            similarity_score = (
                weights['correlation'] * correlation +
                weights['ks_test'] * ks_pvalue +
                weights['cer'] * cer_score
            )

            # Chuẩn hóa về khoảng [0, 1]
            similarity_score = min(1.0, max(0.0, similarity_score))

            return similarity_score

        except Exception as e:
            logger.error(f"Lỗi khi tính độ tương đồng: {str(e)}")
            return 0.0
    
    def find_exact_template(self, data):
        """
        Tìm template chính xác nhất cho dữ liệu đầu vào
        """
        best_template = None
        best_score = float('inf')
        best_offset = 0
        
        # Chuẩn hóa dữ liệu đầu vào
        normalized_data = self.normalize_data(data)
        
        for template_id, template in self.templates.items():
            # Tính toán độ lệch tối thiểu
            min_diff = float('inf')
            best_offset = 0
            
            # Tìm vị trí offset tốt nhất
            for offset in range(len(template['data'])):
                diff = self.calculate_exact_difference(normalized_data, template['data'], offset)
                if diff < min_diff:
                    min_diff = diff
                    best_offset = offset
            
            if min_diff < best_score:
                best_score = min_diff
                best_template = template
                best_offset = best_offset
        
        return best_template, best_offset, best_score

    def calculate_exact_difference(self, data1, data2, offset):
        """
        Tính toán chính xác sự khác biệt giữa hai chuỗi dữ liệu
        """
        if len(data1) > len(data2):
            return float('inf')
            
        diff = 0
        for i in range(len(data1)):
            diff += abs(data1[i] - data2[i + offset])
        return diff

    def normalize_data(self, data):
        """
        Chuẩn hóa dữ liệu để so sánh chính xác hơn
        """
        if isinstance(data, dict):
            return {k: self.normalize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.normalize_data(x) for x in data]
        elif isinstance(data, (int, float)):
            return float(data)
        return data
    
    def compress_non_loss(self, data):
        """
        Nén dữ liệu với độ chính xác 100%
        """
        try:
            # Chuẩn hóa dữ liệu đầu vào
            normalized_data = self.normalize_data(data)
            
            # Tìm template phù hợp nhất
            template, offset, score = self.find_exact_template(normalized_data)
            
            if template is None:
                # Nếu không tìm thấy template phù hợp, tạo template mới
                template_id = self.create_template(normalized_data)
                template = self.templates[template_id]
                offset = 0
                differences = []
            else:
                # Tính toán chính xác sự khác biệt
                differences = self.calculate_exact_differences(normalized_data, template['data'], offset)
            
            # Tạo metadata cho việc giải nén
            metadata = {
                'template_id': template['id'],
                'offset': offset,
                'differences': differences,
                'original_length': len(normalized_data),
                'compression_type': 'non_loss'
            }
            
            # Lưu template vào cache nếu chưa có
            if template['id'] not in self.template_cache:
                self.template_cache[template['id']] = template
            
            # Cập nhật thống kê
            self.update_template_metrics(template['id'])
            
            return {
                'metadata': metadata,
                'compressed_size': len(str(metadata)),
                'original_size': len(str(normalized_data)),
                'compression_ratio': len(str(metadata)) / len(str(normalized_data))
            }
            
        except Exception as e:
            logger.error(f"Lỗi khi nén dữ liệu: {str(e)}")
            return None

    def calculate_exact_differences(self, data1, data2, offset):
        """
        Tính toán chính xác các điểm khác biệt
        """
        differences = []
        for i in range(len(data1)):
            diff = data1[i] - data2[i + offset]
            if abs(diff) > 1e-10:  # Ngưỡng cho số thực
                differences.append({
                    'position': i,
                    'value': diff
                })
        return differences

    def decompress_non_loss(self, compressed_data):
        """
        Giải nén dữ liệu với độ chính xác 100%
        """
        try:
            metadata = compressed_data['metadata']
            template = self.template_cache.get(metadata['template_id'])
            
            if template is None:
                template = self.templates[metadata['template_id']]
                self.template_cache[metadata['template_id']] = template
            
            # Khôi phục dữ liệu gốc
            original_data = []
            template_data = template['data']
            offset = metadata['offset']
            
            for i in range(metadata['original_length']):
                if i < len(template_data) - offset:
                    value = template_data[i + offset]
                else:
                    value = 0
                    
                # Áp dụng các điểm khác biệt
                for diff in metadata['differences']:
                    if diff['position'] == i:
                        value += diff['value']
                        
                original_data.append(value)
            
            return original_data
            
        except Exception as e:
            logger.error(f"Lỗi khi giải nén dữ liệu: {str(e)}")
            return None
    