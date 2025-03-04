import requests
from ummalqura.hijri_date import Umalqurra
import unicodedata
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsMofaGovSa(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.mofa.gov.sa/ar/'
        self.speaker = speaker
        self.country = 'Saudi Arabia'
        self.filename_exeption = 'parsers/mofa_gov_sa/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        
    def get(self) -> None:
        try:
            link = self.domain + 'ministry/statements/Pages/default.aspx'
            statements = self.news_content_response(link)
            links = self.get_links_from_search_news(statements)
            self.get_links_content(links)
        except Exception as ex:
            self.logger.error(ex)
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def get_links_from_search_news(self, search_news: str) -> list:
        links = []
        links_set = set()
        soup = BeautifulSoup(search_news, 'html.parser')
        titles = soup.find_all('div', class_='card-body')
        if not titles:
            return None
        for title in titles:
            dateblock = title.find('span', class_='card-date')
            if not dateblock:
                continue
            date_obj = self.hijri_to_gregorian(dateblock.text.strip())
            if date_obj < self.stop_date_create:
                for news_keyword in self.get_search_terms():
                    if news_keyword in str(title):
                        a_teg = title.find('a')
                        if a_teg:
                            link = a_teg.get('href')
                            if link not in links_set:
                                links_set.add(link)
                                if not self.db_check_link(link, self.speaker):
                                    res = {
                                        'link':link,
                                        'search_keyword':news_keyword,
                                        'date':date_obj.strftime("%Y-%m-%d"),
                                    }
                                    links.append(res)
                                    break
        return links
    
    def get_links_content(self, datas: list) -> None:
        for data in datas:
            try:
                link = data['link']
                if link in self.exception_links:
                    continue
                page_content = self.news_content_response(link)
                soup = BeautifulSoup(page_content, 'html.parser')
                res = self.get_result_dict(data['search_keyword'], self.domain, link, self.speaker, self.country)
                res['news_title']=self.clear_text(soup.find('span',id='DeltaPlaceHolderPageTitleInTitleArea').get_text())
                res['news_body']=self.clear_text(soup.find('div',class_='article-content').get_text())
                res['news_date']=data['date']
                res.update(self.check_aws_bedrock(self.speaker, res))
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(ex)

    def get_news_create(self, createdby: BeautifulSoup) -> str:
        if not createdby:
            return '', True
        arabic_date = createdby.get_text()
        arabic_months_dict = self.arabic_months_dict()
        day, arabic_month, year = arabic_date.split()
        month = arabic_months_dict.get(arabic_month)
        date_obj = datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
        stop_parse = False
        if date_obj < self.stop_date_create:
            stop_parse = True
        return date_obj.strftime("%Y-%m-%d"), stop_parse

    def news_content_response(self, link: str, count_try: int = 0) -> str:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with news content. Link: {link}')
        try:
            headers = self.get_headers()
            response = requests.get(
                url=link,
                headers=headers,
                proxies=self.get_proxy())
            response.raise_for_status()
            return response.text
        except Exception as ex:
            # print(ex)
            pass
        finally:
            if 'response' in locals() and isinstance(response, requests.Response):
                response.close()
        return self.news_content_response(link, count_try + 1)
    
    def get_headers(self) -> dict:
        return {
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
                "Connection": "keep-alive",
            } 
    
    def normalize_arabic(self, text):
        text = unicodedata.normalize("NFKC", text)
        text = text.replace("ـ", "")
        text = text.strip()
        return text

    def hijri_to_gregorian(self, hijri_date: str):
        hijri_months = {
            "محرم": 1, "صفر": 2, "ربيع الأول": 3, "ربيع الثاني": 4, 
            "جمادى الأولى": 5, "جمادى الأولىٰ": 5,
            "جمادى الثانية": 6, "جمادى الآخرة": 6,
            "رجب": 7, "شعبان": 8, "رمضان": 9, "شوال": 10, "ذو القعدة": 11, "ذو الحجة": 12
        }
        hijri_date = self.normalize_arabic(hijri_date)
        parts = hijri_date.split("/")
        if len(parts) != 3:
            raise ValueError(f"Некорректный формат даты: {hijri_date}")
        day, month_ar, year = parts
        month_ar = month_ar.strip()
        if month_ar not in hijri_months:
            raise ValueError(f"Неизвестный арабский месяц: '{month_ar}'")
        month = hijri_months[month_ar]
        ummalqura = Umalqurra()
        g_year, g_month, g_day = ummalqura.hijri_to_gregorian(int(year), month, int(day))
        return datetime(g_year, g_month, g_day)