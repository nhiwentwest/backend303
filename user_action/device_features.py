DEVICE_FEATURES = {
    "yolo-fan": [
        {"feature": "toggle_power", "feed": "yolo-fan", "type": "toggle", "values": [0, 1], "label": "Bật/Tắt quạt"},
        {"feature": "switch_mode", "feed": "yolo-fan-mode-select", "type": "toggle", "values": [0, 1], "label": "Chuyển chế độ Auto/Manual"},
        {"feature": "adjust_temp_threshold", "feed": "temperature-var", "type": "slider", "min": 0, "max": 100, "step": 1, "label": "Điều chỉnh ngưỡng nhiệt độ"},
        {"feature": "adjust_fan_speed", "feed": "yolo-fan-speed", "type": "slider", "min": 0, "max": 100, "step": 10, "label": "Điều chỉnh tốc độ quạt"}
    ],
    "yolo-light": [
        {"feature": "toggle_power", "feed": "yolo-led", "type": "toggle", "values": [0, 1], "label": "Bật/Tắt đèn"},
        {"feature": "switch_mode", "feed": "yolo-led-mode-select", "type": "toggle", "values": [0, 1], "label": "Chuyển chế độ Auto/Manual"},
        {"feature": "adjust_brightness_threshold", "feed": "light-var", "type": "slider", "min": 0, "max": 100, "step": 1, "label": "Điều chỉnh ngưỡng sáng"},
        {"feature": "select_led_num", "feed": "yolo-led-num", "type": "slider", "min": 1, "max": 10, "step": 1, "label": "Chọn số lượng đèn"}
    ],
    "yolo-device": []  # Thiết bị mặc định, không có tính năng điều khiển
}
