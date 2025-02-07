import cloudscraper
import re
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json



class NewsJordantimesCom(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.mfa.gov.jo/'
        self.speaker = speaker
        self.country = 'Jordan'
        self.filename_exeption = 'parsers/jordantimes_com/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms(return_value=True):
                page = 0
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
        titles = soup.find_all('li', class_='search-result')
        if not titles:
            return None
        for title in titles:
            search_info = title.find('p',class_='search-info')
            if search_info:
                text = search_info.get_text(strip=True)
                match = re.search(r'(\d{2}/\d{2}/\d{4}) - (\d{2}:\d{2})', text)
                if match:
                    date_part = match.group(1)
                    time_part = match.group(2)
                    date_obj = datetime.strptime(f"{date_part} {time_part}", "%m/%d/%Y %H:%M")
                    if date_obj < self.stop_date_create:
                        continue
                a_teg = title.find('a')
                if a_teg:
                    link = a_teg.get('href')
                    if not self.db_check_link(link, self.speaker):
                        links.append(link)
        return links
    
    def get_links_content(self, links: list, search_keyword: str) -> None:
        for link in links:
            try:
                if link in self.exception_links:
                    continue
                page_content = self.news_content_response(link)
                soup = BeautifulSoup(page_content, 'html.parser')
                date, stop_parse = self.get_news_create(soup.find('div',class_='news-info'))
                if stop_parse:
                    self.exception_links.append(link)
                    continue
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                res['news_title']=self.clear_text(soup.find('h1').get_text())
                res['news_body']=self.clear_text(soup.find('div',class_='news-body').get_text())
                res['news_date']=date
                res['is_about']=self.check_aws_bedrock(self.speaker, res, lang='en')
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(f'{ex}, link: {link}')
    
    def get_news_create(self, createdby: BeautifulSoup) -> str:
        if not createdby:
            return '', True
        date = createdby.get_text(strip=True)
        parts = date.split(" - ")
        date_str = parts[1]
        date_str = date_str.replace('Last updated at','').strip()
        date_obj = datetime.strptime(date_str, "%b %d,%Y")
        stop_parse = False
        if date_obj < self.stop_date_create:
            stop_parse = True
        return date_obj.strftime("%Y-%m-%d"), stop_parse

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
            encoded_search = urllib.parse.quote(news_keyword)
            response = client.get(f'https://jordantimes.com/search/site/{encoded_search}?page={page}', 
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
