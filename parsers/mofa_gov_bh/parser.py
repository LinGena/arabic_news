import requests
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsMofaGovBh(CheckNewsModel):
    def __init__(self, speakers: list[str]):
        super().__init__()
        self.domain = 'https://www.mofa.gov.bh/ar/'
        self.speakers = speakers
        self.country = 'Bahrain'
        self.filename_exeption = 'parsers/mofa_gov_bh/exception_links.json'
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
                    else:
                        self.get_links_content(links, news_keyword)
                    page += 1
        except Exception as ex:
            self.logger.error(ex)
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def get_links_from_search_news(self, search_news: str) -> list:
        links = []
        soup = BeautifulSoup(search_news, 'html.parser')
        titles = soup.find_all('div', class_='search-results-wrapper')
        if not titles:
            return None
        for title in titles:
            a_teg = title.find('a')
            if a_teg:
                link = self.domain + a_teg.get('href')
                if not self.db_check_link(link, ', '.join(self.speakers)):
                    links.append(link)
        return links
    
    def get_links_content(self, links: list, search_keyword: str) -> None:
        for link in links:
            try:
                if link in self.exception_links:
                    continue
                page_content = self.news_content_response(link)
                soup = BeautifulSoup(page_content, 'html.parser')
                news_block = soup.find('div',class_='news-detail-content-area')
                news_date, stop_parse = self.get_news_create(soup.find('h6',class_='common-icon-text'))
                if stop_parse:
                    self.exception_links.append(link)
                    continue
                i = 1
                for speaker in self.speakers:
                    news_title = ''
                    news_title_block = news_block.find('h4')
                    if news_title_block:
                        news_title = news_title_block.get_text()
                    res = self.get_result_dict(search_keyword, self.domain, link, ', '.join(self.speakers), self.country)
                    res['news_title']=self.clear_text(news_title)
                    res['news_body']=self.clear_text(news_block.get_text().replace(news_title,'').strip())
                    res['news_date']=news_date
                    res.update(self.check_aws_bedrock(speaker, res))
                    if res['is_about'] or i == 1:
                        if res['is_about']:
                            res['speaker'] = speaker
                        self.db_client.insert_row(res)
                    i += 1
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
            headers = self.get_heders()
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

    def get_response(self, news_keyword: str, page: int = 1, pagesize: int = 16, count_try: int = 0) -> str:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with bna_response. News_keyword: {news_keyword}, Page: {page}')
        try:
            headers = self.get_heders()
            params = {
                'keyword': str(news_keyword),
                'page': str(page),
                'pageSize': str(pagesize),
            }
            response = requests.get(
                f'{self.domain}search',
                headers=headers,
                proxies=self.get_proxy(),
                params=params)
            response.raise_for_status()
            return response.text
        except Exception as ex:
            pass
        finally:
            if 'response' in locals() and isinstance(response, requests.Response):
                response.close()
        return self.get_response(news_keyword, page, pagesize, count_try + 1)
    
    def get_heders(self) -> dict:
        return {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        }