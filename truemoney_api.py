from curl_cffi import requests # ใช้ตัวนี้แทน requests เดิม
import re
import json

class TrueMoneyWallet:
    def __init__(self, phone_number):
        self.phone = phone_number
        self.base_url = "https://gift.truemoney.com/campaign/vouchers/"
        
    def extract_voucher_code(self, url):
        try:
            url = url.strip()
            patterns = [
                r'v=([a-zA-Z0-9]{10,})',
                r'vouchers/([a-zA-Z0-9]{10,})'
            ]
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            if re.match(r'^[a-zA-Z0-9]{10,}$', url):
                return url
            return None
        except:
            return None

    def redeem_voucher(self, voucher_url):
        voucher_code = self.extract_voucher_code(voucher_url)
        if not voucher_code:
            return {'success': False, 'message': 'ลิงก์ซองอั่งเปาไม่ถูกต้อง'}

        try:
            url = f"{self.base_url}{voucher_code}/redeem"
            
            # Headers แบบเต็มสูบ
            headers = {
                'accept': 'application/json',
                'accept-encoding': 'gzip, deflate, br',
                'accept-language': 'en-US,en;q=0.9',
                'content-type': 'application/json',
                'origin': 'https://gift.truemoney.com',
                'referer': f'https://gift.truemoney.com/campaign/?v={voucher_code}',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
            }
            
            payload = {'mobile': self.phone, 'voucher_hash': voucher_code}
            
            # ใช้ impersonate="chrome110" เพื่อหลอก Server ว่าเราคือ Chrome จริงๆ
            response = requests.post(
                url, 
                json=payload, 
                headers=headers, 
                timeout=10,
                impersonate="chrome110" 
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # --- Debug: Print ดูข้อมูลดิบจาก TrueMoney (ลบออกได้ภายหลัง) ---
                print(f"[DEBUG] Raw Response: {json.dumps(result, ensure_ascii=False)}")
                # -----------------------------------------------------------

                status_code = result.get('status', {}).get('code')
                
                if status_code == 'SUCCESS':
                    data = result.get('data', {})
                    
                    # จุดแก้ไข: ดึงยอดเงินจาก my_ticket -> amount_baht
                    amount_str = data.get('my_ticket', {}).get('amount_baht', 0)
                    
                    # กันพลาด: กรณีหาไม่เจอ ลองดึงจาก voucher object (เผื่อ API เปลี่ยน)
                    if float(amount_str) == 0:
                        amount_str = data.get('voucher', {}).get('redeemed_amount_baht', 0)
                    
                    amount = float(amount_str)
                    
                    return {'success': True, 'amount': amount, 'message': f'เติมสำเร็จ {amount} บาท'}
                
                error_map = {
                    'CANNOT_GET_OWN_VOUCHER': 'เติมเข้าเบอร์คนสร้างซองไม่ได้',
                    'TARGET_USER_REDEEMED': 'คุณเคยรับซองนี้ไปแล้ว',
                    'VOUCHER_OUT_OF_STOCK': 'ซองหมดแล้ว',
                    'VOUCHER_EXPIRED': 'ซองหมดอายุ'
                }
                return {'success': False, 'message': error_map.get(status_code, f'Error: {status_code}')}
            
            return {'success': False, 'message': f'HTTP Error: {response.status_code} (ยังคงโดนบล็อก)'}
            
        except Exception as e:
            return {'success': False, 'message': f'System Error: {str(e)}'}