import numpy as np
from lossless_compression import LosslessCompressor
import pytest

# --- Helper: Mock decompress (giả lập, cần bạn thay thế bằng bản chuẩn nếu có) ---
def mock_decompress(encoded_stream, block_size, num_buffers, original_length):
    buffers = []
    data = []
    i = 0
    while i < len(encoded_stream):
        code = encoded_stream[i]
        # Chỉ so sánh marker nếu code là int
        if isinstance(code, (int, np.integer)) and code == 0xFE:
            i += 1
            block_size = encoded_stream[i]
            buffers = []
        elif isinstance(code, (int, np.integer)) and code == 0xFF:
            i += 1
            overwrite_idx = encoded_stream[i]
            i += 1
            block = np.array(encoded_stream[i])
            while len(buffers) <= overwrite_idx:
                buffers.append(np.zeros(block_size))
            buffers[overwrite_idx] = block.copy()
            data.extend(block.tolist())
        elif isinstance(code, (int, np.integer)) and code == 0xFD:
            i += 1
            block = np.array(encoded_stream[i])
            if len(buffers) < num_buffers:
                buffers.append(block.copy())
            else:
                buffers[0] = block.copy()
            data.extend(block.tolist())
        elif isinstance(code, (int, np.integer)) and code < num_buffers:
            block = buffers[code]
            data.extend(block.tolist())
        else:
            # Không còn trường hợp block gốc không marker
            pass
        i += 1
    return np.array(data[:original_length])

# --- Test KS test ---
def test_ks_exchangeable_true():
    compressor = LosslessCompressor()
    a = np.arange(24)
    b = np.arange(24)
    assert compressor.ks_exchangeable(a, b) == True

def test_ks_exchangeable_false():
    compressor = LosslessCompressor()
    a = np.arange(24)
    b = np.arange(24) + 1000
    assert compressor.ks_exchangeable(a, b) == False

# --- Test buffer management & marker ---
def test_encode_block_buffer_add_and_overwrite():
    compressor = LosslessCompressor({'num_buffers': 2})
    block1 = np.arange(24)
    block2 = np.arange(24) + 100
    block3 = np.arange(24) + 200
    compressor.encode_block(block1)
    compressor.encode_block(block2)
    # Buffer đã đầy, block3 sẽ ghi đè buffer đầu tiên, marker 0xFF xuất hiện
    compressor.encode_block(block3)
    count = sum(
        1 for x in compressor.encoded_stream
        if isinstance(x, int) and x == compressor.BUFFER_OVERWRITE_MARKER
    )
    assert count == 1

# --- Test compress logic & round-trip (lossless) ---
def test_compress_and_round_trip():
    compressor = LosslessCompressor({'block_size': 8, 'num_buffers': 2, 'similarity_threshold': 0.01})
    data = np.tile(np.arange(8), 10)  # Dữ liệu lặp lại
    result = compressor.compress(data)
    recovered = mock_decompress(result['encoded_stream'], result['block_size'], result['num_buffers'], result['original_length'])
    print("Original data:", data)
    print("Recovered data:", recovered)
    print("Encoded stream:", result['encoded_stream'])
    print("Shape original:", data.shape, "Shape recovered:", recovered.shape)
    print("Allclose:", np.allclose(recovered, data))
    if recovered.shape == data.shape:
        print("Diff:", recovered - data)
    assert np.allclose(recovered, data)

# --- Test marker khi đổi block size ---
def test_block_size_change_marker():
    compressor = LosslessCompressor({'block_size': 8})
    compressor.change_block_size(16)
    assert compressor.encoded_stream[0] == compressor.BLOCKSIZE_CHANGE_MARKER
    assert compressor.encoded_stream[1] == 16

# --- Test compression ratio logic ---
def test_simulate_compress_ratio():
    compressor = LosslessCompressor({'block_size': 8, 'num_buffers': 2, 'similarity_threshold': 0.01})
    data = np.tile(np.arange(8), 10)
    ratio, hit_count = compressor.simulate_compress(data, 8, 2, 0.01)
    assert ratio > 1.0  # Dữ liệu lặp lại, tỷ lệ nén phải tốt

# --- Test logging (nếu cần, có thể kiểm tra log bằng caplog của pytest) ---
# def test_logging(caplog):
#     compressor = LosslessCompressor()
#     block = np.arange(24)
#     with caplog.at_level('INFO'):
#         compressor.encode_block(block)
#     assert "[RAW]" in caplog.text

def test_hit_ratio_and_log(capfd):
    block_size = 4
    num_buffers = 2
    # Dữ liệu số nguyên hoàn toàn
    data = np.concatenate([
        np.ones(block_size, dtype=int) * 10,   # Block 1
        np.ones(block_size, dtype=int) * 10,   # Block 2 (giống block 1)
        np.ones(block_size, dtype=int) * 10,   # Block 3 (giống block 1)
        np.arange(block_size, dtype=int) + 10,  # Block 4 (khác)
        np.arange(block_size, dtype=int) + 20,  # Block 5 (khác)
    ])
    compressor = LosslessCompressor({
        'block_size': block_size,
        'num_buffers': num_buffers,
        'similarity_threshold': 0.01  # Đặt thấp để chắc chắn nhận ra block giống
    })
    result = compressor.compress(data)
    print("Encoded stream:", result['encoded_stream'])
    print("Hit ratio:", result['hit_ratio'])
    print("Compression ratio:", result['compression_ratio'])
    out, err = capfd.readouterr()
    # Kiểm tra log có [HIT] và [MISS]
    assert "[HIT]" in out or "[HIT]" in err
    assert "[MISS]" in out or "[MISS]" in err
    # Hit ratio phải đúng (2 hit trên 5 block)
    assert np.isclose(result['hit_ratio'], 2/5)

if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__]))
