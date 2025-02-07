import cloudscraper
import re
from ummalqura.hijri_date import Umalqurra
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsMofaGovQa(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://mofa.gov.qa'
        self.speaker = speaker
        self.country = 'Qatar'
        self.filename_exeption = 'parsers/mofa_gov_qa/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
                page = 1
                while True:
                    search_news = self.get_response(news_keyword, page)
                    links = self.get_links_from_search_news(search_news)
                    if not links:
                        break
                    self.get_links_content(links, news_keyword)
                    page += 1
        except Exception as ex:
            self.logger.error(ex)
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def get_links_from_search_news(self, search_news: str) -> list:
        links = []
        soup = BeautifulSoup(search_news, 'html.parser')
        titles = soup.find_all('div', class_='sf-search-results')
        if not titles:
            return None
        for title in titles:
            a_teg = title.find('a')
            if a_teg:
                link = a_teg.get('href')
                date_obj = self.extract_hijri_date_from_url(link)
                if date_obj < self.stop_date_create:
                    continue
                date = date_obj.strftime("%Y-%m-%d")
                if not self.db_check_link(link, self.speaker):
                    res = {
                        'link': link,
                        'date': date
                    }
                    links.append(res)
        return links
    
    def get_links_content(self, datas: list, search_keyword: str) -> None:
        for data in datas:
            try:
                link = data['link']
                if link in self.exception_links:
                    continue
                page_content = self.news_content_response(link)
                soup = BeautifulSoup(page_content, 'html.parser')
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                res['news_title']=self.clear_text(soup.find('h3',class_='news-detail-title').get_text())
                res['news_body']=self.clear_text(soup.find('div',class_='news-detail-content').get_text())
                res['news_date']=data['date']
                res['is_about']=self.check_aws_bedrock(self.speaker, res)
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(f'{ex}, link: {link}')
    
    def news_content_response(self, link: str, count_try: int = 0) -> str:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with news content. Link: {link}')
        try:
            client = cloudscraper.create_scraper()
            response = client.get(link, proxies=self.get_proxy(), headers=self.get_headers())
            response.raise_for_status()
            return response.text
        except Exception as ex:
            # print(ex)
            pass
        finally:
            client.close()
        return self.news_content_response(link, count_try + 1)

    def get_response(self, news_keyword: str, page: int = 1, count_try: int = 0) -> str:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with bna_response. News_keyword: {news_keyword}, Page: {page}')
        try:
            client = cloudscraper.create_scraper()
            params = {
                'indexCatalogue': 'mofasite',
                'searchQuery': f'{news_keyword}',
                'wordsMode': 'AllWords',
                'orderBy': 'Newest',
            }
            response = client.get(f'https://mofa.gov.qa/search/{page}', 
                                  params=params, 
                                  proxies=self.get_proxy(), 
                                  headers=self.get_headers())
            response.raise_for_status()
            return response.text
        except Exception as ex:
            # print(ex)
            pass
        finally:
            client.close()
        return self.get_response(news_keyword, page, count_try + 1)

    def get_headers(self) -> dict:
        return {
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
                "Connection": "keep-alive",
            }

    def extract_hijri_date_from_url(self, url: str):
        match = re.search(r'(\d{4})/(\d{2})/(\d{2})', url)
        if not match:
            return None
        year, month, day = map(int, match.groups())
        ummalqura = Umalqurra()
        g_year, g_month, g_day = ummalqura.hijri_to_gregorian(year, month, day)
        return datetime(g_year, g_month, g_day)