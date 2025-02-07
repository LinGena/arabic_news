import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsDiwanGovQa(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.diwan.gov.qa'
        self.speaker = speaker
        self.country = 'Qatar'
        self.filename_exeption = 'parsers/diwan_gov_qa/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
                page = 1
                while True:
                    print('----- news_keyword =',news_keyword,'page=',page)
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
        titles = soup.find_all('div', class_='list-items__item')
        if not titles:
            return None
        for title in titles:
            date_block = title.find('span', class_='date')
            if not date_block:
                continue
            date_content = date_block.find('text')
            if not date_content:
                continue
            date_arabic = date_content.text.strip()
            date, stop_parse = self.get_news_create(date_arabic)
            if stop_parse:
                continue
            a_teg = title.find('a')
            if a_teg:
                link = self.domain + a_teg.get('href')
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
                res['news_title']=self.clear_text(soup.find('h1').get_text())
                res['news_body']=self.clear_text(soup.find('p').get_text())
                res['news_date']=data['date']
                res['is_about']=self.check_aws_bedrock(self.speaker, res)
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(f'{ex}, link: {link}')
    
    def get_news_create(self, arabic_date: str) -> str:
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
                'query': f'{news_keyword}',
                'type': '3',
                'date_from': '',
                'date_to': '',
                'page': f'{page}',
            }
            response = client.get('https://www.diwan.gov.qa/search', 
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
