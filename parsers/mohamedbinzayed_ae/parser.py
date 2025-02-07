import cloudscraper
import json
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsMohamedbinzayedAe(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.mohamedbinzayed.ae'
        self.speaker = speaker
        self.country = 'United Arab Emirates'
        self.filename_exeption = 'parsers/mohamedbinzayed_ae/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
                self.total_count = 0
                page = 0
                while True:
                    search_news = self.get_response(news_keyword, page)
                    links = self.get_links_from_search_news(search_news)
                    if not links:
                        break
                    self.get_links_content(links, news_keyword)
                    page += 6
                    if self.total_count < page:
                        break
        except Exception as ex:
            self.logger.error(ex)
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def get_links_from_search_news(self, search_news: dict) -> list:
        links = []
        self.total_count = int(search_news['data']['GQLResults']['results']['totalCount'])
        titles = search_news['data']['GQLResults']['results']['items']
        if not titles:
            return None
        for title in titles:
            link = self.domain + title['item']['url']
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
                script = soup.find('script',id='__JSS_STATE__').text.strip()
                data = json.loads(script).get("sitecore", {}).get("route", {})
                value_date = data.get("fields", {}).get("Date", {}).get("value", None)
                date, stop_parse = self.get_news_create(value_date)
                if stop_parse:
                    self.exception_links.append(link)
                    continue
                components = data.get("placeholders", {}).get("jss-main", [])
                description_value = ''
                for component in components:
                    if component.get("componentName") == "Content":
                        description_value = component.get("fields", {}).get("Description", {}).get("value", '')
                        break
                description = BeautifulSoup(description_value,'html.parser')
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                res['news_title']=self.clear_text(soup.find('h1').get_text())
                res['news_body']=self.clear_text(description.get_text())
                res['news_date']=date
                res['is_about']=self.check_aws_bedrock(self.speaker, res)
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(f'{ex}, link: {link}')
    
    def get_news_create(self, createdby: BeautifulSoup) -> str:
        if not createdby:
            return '', True
        date_obj = datetime.strptime(createdby, "%Y-%m-%dT%H:%M:%SZ")
        stop_parse = False
        if date_obj < self.stop_date_create:
            stop_parse = True
        return date_obj.strftime("%Y-%m-%d"), stop_parse

    def news_content_response(self, link: str, count_try: int = 0) -> str:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with news content. Link: {link}')
        try:
            client = cloudscraper.create_scraper()
            response = client.get(link, proxies=self.get_proxy())
            response.raise_for_status()
            return response.text
        except Exception as ex:
            # print(ex)
            pass
        finally:
            client.close()
        return self.news_content_response(link, count_try + 1)

    def get_response(self, news_keyword: str, page: int = 0, count_try: int = 0) -> dict:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with bna_response. News_keyword: {news_keyword}, Page: {page}')
        try:
            client = cloudscraper.create_scraper()
            json_data = [
                {
                    'variables': {
                        'pageSize': 6,
                        'skip': f'{page}',
                        'keyword': f'{news_keyword}',
                        'filters': [],
                        'language': 'ar',
                    },
                    'extensions': {
                        'persistedQuery': {
                            'version': 1,
                            'sha256Hash': 'e59b7ed509b4cb3a0c0263e51d0d4aa06f0d26b7ef48f2e6a25e71a3df0a262b',
                        },
                    },
                },
            ]
            response = client.post(f'https://www.mohamedbinzayed.ae/sitecore/api/graph/items/web',
                                   json=json_data,
                                   proxies=self.get_proxy())
            response.raise_for_status()
            return response.json()[0]
        except Exception as ex:
            # print(ex)
            pass
        finally:
            client.close()
        return self.get_response(news_keyword, page, count_try + 1)