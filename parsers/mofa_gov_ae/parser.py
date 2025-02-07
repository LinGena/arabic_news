import cloudscraper
import re
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsMofaGovAe(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.mofa.gov.ae'
        self.speaker = speaker
        self.country = 'United Arab Emirates'
        self.filename_exeption = 'parsers/mofa_gov_ae/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms(return_value=True):
                if news_keyword == 'Al-Aqsa':
                    news_keyword = 'Aqsa'
                page = 1
                self.parse_next = True
                while self.parse_next:
                    print('page = ',page, 'word =',news_keyword)
                    search_news = self.get_response(news_keyword, page)
                    links = self.get_links_from_search_news(search_news)
                    if links:
                        self.get_links_content(links, news_keyword)
                    page += 1
        except Exception as ex:
            self.logger.error(ex)
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def get_links_from_search_news(self, search_news: str) -> list:
        links = []
        soup = BeautifulSoup(search_news, 'html.parser')
        titles = soup.find_all('div', class_='item-info')
        if not titles:
            self.parse_next = False
            return None
        for title in titles:
            try:
                a_teg = title.find('a')
                if a_teg:
                    link = a_teg.get('href')
                    match = re.search(r"(\d{2})-(\d{2})-(\d{4})", link)
                    if not match:
                        continue
                    day, month, year = match.groups()
                    date_obj = datetime.strptime(f"{day}-{month}-{year}", "%d-%m-%Y")
                    if date_obj < self.stop_date_create:
                        continue
                    date = date_obj.strftime("%Y-%m-%d")
                    link = self.domain + link
                    if not self.db_check_link(link, self.speaker):
                        res = {
                            'link': link,
                            'date': date
                        }
                        links.append(res)
            except:
                pass
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
                details_container = soup.find("div", class_="details-container")
                full_text = ''
                if details_container:
                    text_list = [p.get_text(strip=True) for p in details_container.find_all("p")]
                    full_text = " ".join(text_list)
                res['news_title']=self.clear_text(soup.find('div',class_='details-info').find('h2').get_text())
                res['news_body']=self.clear_text(full_text)
                res['news_date']=data['date']
                res['is_about']=self.check_aws_bedrock(self.speaker, res, lang='en')
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

    def get_response(self, news_keyword: str, page: int = 0, count_try: int = 0) -> str:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with bna_response. News_keyword: {news_keyword}, Page: {page}')
        try:
            client = cloudscraper.create_scraper()
            cookies = {
                'ldsc#lang': 'en',
            }
            data = {
                'query': f'{news_keyword}',
                'page': f'{page}',
                'templatesIDs[]': [
                    '{2F75C8AF-35FC-4A88-B585-7595203F442C}',
                    '{5EB1B0C0-2264-4A03-A89E-EF56737F2408}',
                ],
                'wordOptions': '1',
            }
            response = client.post('https://www.mofa.gov.ae/api/features/Search/advancedSearchResult', 
                                  data=data,
                                  proxies=self.get_proxy(), 
                                  cookies=cookies)
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