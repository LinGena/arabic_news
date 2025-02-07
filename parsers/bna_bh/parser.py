import requests
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel


class NewsBnaBh(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.bna.bh/'
        self.country = 'Bahrain'
        self.speaker = speaker
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
                self.stop_parse_next = False
                page = 1
                while not self.stop_parse_next:
                    search_news = self.bna_response(news_keyword, page)
                    links = self.get_links_from_search_news(search_news)
                    if not links:
                        break
                    self.get_links_content(links, news_keyword)
                    page += 1
        except Exception as ex:
            self.logger.error(ex)

    def get_links_from_search_news(self, search_news: str) -> list:
        links = []
        soup = BeautifulSoup(search_news, 'html.parser')
        titles = soup.find_all('h2', class_='title')
        if not titles:
            return None
        for title in titles:
            a_teg = title.find('a')
            if a_teg:
                link = self.domain + a_teg.get('href')
                if not self.db_check_link(link, self.speaker):
                    links.append(link)
        return links
    
    def get_links_content(self, links: list, search_keyword: str) -> None:
        for link in links:
            try:
                page_content = self.news_content_response(link)
                soup = BeautifulSoup(page_content, 'html.parser')
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                res['news_title']=soup.find('h1',class_='h2 title').get_text()
                res['news_body']=self.get_body(soup)
                res['news_date']=self.get_news_create(soup.find('dd',class_='createdby'))
                if self.stop_parse_next:
                    break
                res['is_about']=self.check_aws_bedrock(self.speaker, res)
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(ex)
    
    def get_news_create(self, createdby: BeautifulSoup) -> str:
        arabic_date = createdby.get_text()
        arabic_months_dict = self.arabic_months_dict()
        day, arabic_month, year = arabic_date.split()
        month = arabic_months_dict.get(arabic_month)
        date_obj = datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
        if date_obj < self.stop_date_create:
            self.stop_parse_next = True
        return date_obj.strftime("%Y-%m-%d")
        
    def get_body(self, soup: BeautifulSoup) -> str:
        section = soup.find_all("section")[-1]
        return section.get_text()

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

    def bna_response(self, news_keyword: str, page: int = 1, pagesize: int = 30, count_try: int = 0) -> str:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with bna_response. News_keyword: {news_keyword}, Page: {page}')
        try:
            headers = self.get_heders()
            json_data = {
                'RowNumber': 0,
                'NewsKeyword': str(news_keyword),
                'RowNumberArchive': 0,
                'pageIndex': int(page),
                'pagesize': str(pagesize),
            }
            response = requests.post(
                'https://www.bna.bh/bnaWebService.aspx/fnGetWebsiteSearchNew',
                headers=headers,
                proxies=self.get_proxy(),
                json=json_data)
            response.raise_for_status()
            data : dict = response.json()
            return data.get('d',[])[0]
        except Exception as ex:
            # print(ex)
            pass
        finally:
            if 'response' in locals() and isinstance(response, requests.Response):
                response.close()
        return self.bna_response(news_keyword, page, pagesize, count_try + 1)
    
    def get_heders(self) -> dict:
        return {
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
                'x-requested-with': 'XMLHttpRequest',
            }