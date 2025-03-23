import os
import re
import json
import random
from datetime import datetime, timedelta
from proxies.proxy_manager import get_proxies
from utils.logger import Logger
from db.core import PostgreSQLTable
from utils.func import load_from_file_json, write_to_file_json


class Functions():
    def __init__(self):
        self.max_count_try = 20
        self.stop_date_create = datetime.today() - timedelta(days=140)
        self.proxies_list = get_proxies()
        self.logger = Logger().get_logger(__name__)
        self.db_client = PostgreSQLTable(os.getenv("TABLE_NAME"))

    def get_proxy(self) -> dict:
        random.shuffle(self.proxies_list)
        proxy = self.proxies_list[0]
        return {'http':proxy, 'https':proxy}
    
    def arabic_months_dict(self) -> dict:
        return {
            "يناير": "January", 
            "فبراير": "February", 
            "مارس": "March", 
            "أبريل": "April",
            "مايو": "May", 
            "يونيو": "June", 
            "يوليو": "July", 
            "أغسطس": "August",
            "سبتمبر": "September", 
            "أكتوبر": "October", 
            "نوفمبر": "November", 
            "ديسمبر": "December"
        }
    
    def arabic_months_dict_second(self) -> dict:
        return {
            "كانون الثاني": "January",
            "شباط": "February",
            "آذار": "March",
            "نيسان": "April",
            "أيار": "May",
            "حزيران": "June",
            "تموز": "July",
            "آب": "August",
            "أيلول": "September",
            "تشرين الأول": "October",
            "تشرين الثاني": "November",
            "كانون الأول": "December"
        }
            
    def arabic_to_western(self) -> dict:
        return {
            "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
            "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        }
    
    def get_search_terms(self, return_value: bool = False) -> list:
        # search_terms = {
        #     "إسرائيل": "Israel",
        #     "فلسطين": "Palestine",
        #     "غزة": "Gaza",
        #     "الضفة الغربية": "West Bank",
        #     "القدس": "Jerusalem",
        #     "حركة حماس": "Hamas",
        #     "وكالة الأمم المتحدة لإغاثة وتشغيل اللاجئين الفلسطينيين": "UNRWA",
        #     "المصلى القبلي": "Al-Aqsa"
        # }
        search_terms = {
            "إسرائيل": "Israel",
            "فلسطين": "Palestine",
            "غزة": "Gaza",
            "الضفة الغربية": "West Bank",
            "القدس": "Jerusalem",
            "حماس": "Hamas",
            "الأونروا": "UNRWA",
            "الأقصى": "Al-Aqsa"
        }
        return list(search_terms.values()) if return_value else list(search_terms.keys())
    
    def db_check_link(self, link: str, speaker: str) -> bool:
        data = {
            "news_link": link,
            "speaker": str(speaker)
            }
        if not self.db_client.get_row(data):
            return False
        return True
    
    def clear_text(self, text: str) -> str:
        value = ''
        if text:
            value = re.sub(r"[^\x20-\x7E\u0400-\u04FF\u0600-\u06FF\u0E00-\u0E7F]+", " ", text)
            value = re.sub(r"\s+", " ", value).strip()
        return value
    
    def get_result_dict(self, search_keyword: str, domain: str, link: str, speaker: str, country: str) -> dict:
        return {
            'search_keyword':search_keyword,
            'source':domain,
            'news_link':link,
            'news_title':'',
            'news_body':'',
            'news_date':'',
            'speaker':speaker,
            'is_about':False,
            'country':country
        }

    def get_exception_links(self, filename) -> list:
        if not os.path.exists(filename):
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            write_to_file_json(filename, [])
        return load_from_file_json(filename)

    def convert_arabic_date_to_iso(self, arabic_date: str) -> str:
        """
        Convert Arabic formatted dates to ISO format (YYYY-MM-DD) for database compatibility

        Args:
            arabic_date: Date in Arabic format (e.g. "3 أغسطس 2014")

        Returns:
            Date in ISO format (e.g. "2014-08-03") or None if conversion fails
        """
        try:
            # First, convert any Arabic numerals to Western numerals
            for ar, en in self.arabic_to_western().items():
                arabic_date = arabic_date.replace(ar, en)

            parts = arabic_date.split()
            if len(parts) != 3:
                self.logger.warning(f"Unexpected date format: {arabic_date}")
                return None

            day = parts[0].zfill(2)  # Pad with leading zero if needed

            # Try both Arabic month dictionaries
            month_name = parts[1]
            month_en = self.arabic_months_dict().get(month_name)

            if not month_en:
                month_en = self.arabic_months_dict_second().get(month_name)

            if not month_en:
                self.logger.warning(f"Unknown month: {month_name} in date {arabic_date}")
                return None

            year = parts[2]

            # Convert to datetime for validation and formatting
            date_obj = datetime.strptime(f"{day} {month_en} {year}", "%d %B %Y")
            return date_obj.strftime("%Y-%m-%d")
        except Exception as e:
            # Log the error and return None
            self.logger.error(f"Error converting date '{arabic_date}': {e}")
            return None