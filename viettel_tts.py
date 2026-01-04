"""
Viettel AI Text-to-Speech API Client
Danh sách 16 giọng đọc chính xác từ Viettel AI
"""

import requests
import json
from dataclasses import dataclass


@dataclass
class VoiceConfig:
    code: str
    name: str
    region: str
    gender: str


# 16 giọng đọc chính xác từ Viettel AI
VOICES = {
    # ===== GIỌNG NAM (5 giọng) =====
    "hn-thanhtung": VoiceConfig("hn-thanhtung", "Thanh Tùng", "Miền Bắc", "Nam"),
    "hue-baoquoc": VoiceConfig("hue-baoquoc", "Bảo Quốc", "Miền Trung", "Nam"),
    "hcm-minhquan": VoiceConfig("hcm-minhquan", "Minh Quân", "Miền Nam", "Nam"),
    "hn-namkhanh": VoiceConfig("hn-namkhanh", "Nam Khánh", "Miền Bắc", "Nam"),
    "hn-tienquan": VoiceConfig("hn-tienquan", "Tiến Quân", "Miền Bắc", "Nam"),
    
    # ===== GIỌNG NỮ (11 giọng) =====
    "hn-quynhanh": VoiceConfig("hn-quynhanh", "Quỳnh Anh", "Miền Bắc", "Nữ"),
    "hcm-diemmy": VoiceConfig("hcm-diemmy", "Diễm My", "Miền Nam", "Nữ"),
    "hue-maingoc": VoiceConfig("hue-maingoc", "Mai Ngọc", "Miền Trung", "Nữ"),
    "hn-phuongtrang": VoiceConfig("hn-phuongtrang", "Phương Trang", "Miền Bắc", "Nữ"),
    "hn-thaochi": VoiceConfig("hn-thaochi", "Thảo Chi", "Miền Bắc", "Nữ"),
    "hn-thanhha": VoiceConfig("hn-thanhha", "Thanh Hà", "Miền Bắc", "Nữ"),
    "hcm-phuongly": VoiceConfig("hcm-phuongly", "Phương Ly", "Miền Nam", "Nữ"),
    "hcm-thuydung": VoiceConfig("hcm-thuydung", "Thùy Dung", "Miền Nam", "Nữ"),
    "hn-thanhphuong": VoiceConfig("hn-thanhphuong", "Thanh Phương", "Miền Bắc", "Nữ"),
    "hn-leyen": VoiceConfig("hn-leyen", "Lệ Yên", "Miền Nam", "Nữ"),
    "hcm-thuyduyen": VoiceConfig("hcm-thuyduyen", "Thùy Duyên", "Miền Nam", "Nữ"),
}


class ViettelTTS:
    BASE_URL = "https://viettelai.vn/tts/speech_synthesis"

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "accept": "*/*"
        })

    def synthesize(
        self,
        text: str,
        voice: str = "hn-quynhanh",
        speed: float = 1.0,
        without_filter: bool = False,
    ) -> bytes:
        payload = {
            "text": text,
            "voice": voice,
            "speed": speed,
            "tts_return_option": 3,
            "token": self.token,
            "without_filter": without_filter
        }

        response = self.session.post(self.BASE_URL, data=json.dumps(payload))

        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type:
                error_data = response.json()
                raise Exception(f"API Error: {error_data}")
            return response.content
        else:
            raise Exception(f"API Error: {response.status_code} - {response.text}")

    def synthesize_to_file(self, text: str, output_path: str, voice: str = "hn-quynhanh", speed: float = 1.0) -> str:
        audio_data = self.synthesize(text, voice, speed)
        with open(output_path, "wb") as f:
            f.write(audio_data)
        return output_path

    @staticmethod
    def list_voices():
        return [
            {"code": k, "name": v.name, "region": v.region, "gender": v.gender}
            for k, v in VOICES.items()
        ]
