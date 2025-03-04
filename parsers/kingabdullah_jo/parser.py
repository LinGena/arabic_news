import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsKingabdullahJo(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.kingabdullah.jo'
        self.speaker = speaker
        self.country = 'Jordan'
        self.filename_exeption = 'parsers/kingabdullah_jo/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
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
        titles = soup.find_all('h3', class_='field-content')
        if not titles:
            return None
        for title in titles:
            date_obj = None
            date_block = title.find_next('span', class_='date-display-single')
            if date_block:
                date_content = date_block.get('content')
                if date_content:
                    date_obj = datetime.strptime(date_content, "%Y-%m-%dT%H:%M:%S%z")
                    date_obj = date_obj.replace(tzinfo=None)
            if date_obj:
                if date_obj < self.stop_date_create:
                    continue
            a_teg = title.find('a')
            if a_teg:
                link = self.domain + a_teg.get('href')
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
                date, stop_parse = self.get_news_create(soup.find('span',{'property':'dc:date'}))
                if stop_parse:
                    self.exception_links.append(link)
                    continue
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                res['news_title']=self.clear_text(soup.find('div',{'property':'dc:title'}).get_text())
                res['news_body']=self.clear_text(soup.find('div',{'property':'content:encoded'}).get_text())
                res['news_date']=date
                res.update(self.check_aws_bedrock(self.speaker, res))
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(f'{ex}, link: {link}')
    
    def get_news_create(self, createdby: BeautifulSoup) -> str:
        if not createdby:
            return '', True
        date_content = createdby.get('content')
        date_obj = datetime.strptime(date_content, "%Y-%m-%dT%H:%M:%S%z")
        date_obj = date_obj.replace(tzinfo=None)
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
            params = {
                'search_api_views_fulltext': f'{news_keyword}',
                'field_date[date]': '',
                'field_date_1[date]': '',
                'type': 'All',
                'page': f'{page}',
            }
            response = client.get('https://www.kingabdullah.jo/ar/search', 
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
