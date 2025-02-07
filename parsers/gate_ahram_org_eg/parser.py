import cloudscraper
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsGateAhramOrgEg(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'http://gate.ahram.org.eg'
        self.speaker = speaker
        self.country = 'Egypt'
        self.filename_exeption = 'parsers/gate_ahram_org_eg/exception_links.json'
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
                    page += 10
        except Exception as ex:
            self.logger.error(ex)
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def get_links_from_search_news(self, search_news: str) -> list:
        links = []
        soup = BeautifulSoup(search_news, 'html.parser')
        block = soup.find('div', id='ContentPlaceHolder1_resultDiv')
        if not block:
            return links
        block = block.find_next('div',class_='row')
        titles = [div for div in block.find_all("div") if div.has_attr("id")]
        if not titles:
            return None
        for title in titles:
            dateblock = title.find('p', class_='bref')
            date_obj = None
            if dateblock:
                try:
                    date = dateblock.get_text().strip()
                    date_obj = datetime.strptime(date, "%m/%d/%Y %I:%M:%S %p")
                except:
                    pass
            if date_obj:
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
                date, stop_parse = self.get_news_create(soup.find('div',id='ContentPlaceHolder1_divdate'))
                if stop_parse:
                    self.exception_links.append(link)
                    continue
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                res['news_title']=self.clear_text(soup.find('h1',id='ContentPlaceHolder1_divTitle').get_text())
                res['news_body']=self.clear_text(soup.find('div',id='ContentPlaceHolder1_divContent').get_text())
                res['news_date']=date
                res['is_about']=self.check_aws_bedrock(self.speaker, res)
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(f'{ex}, link: {link}')
    
    def get_news_create(self, createdby: BeautifulSoup) -> str:
        if not createdby:
            return '', True
        createdby = createdby.find('span')
        if not createdby:
            return '', True
        date = createdby.get_text()
        date_obj = datetime.strptime(date.strip(), "%d-%m-%Y | %H:%M")
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
                'StartRowIndex': f'{page}',
            }
            encoded_search = urllib.parse.quote(news_keyword)
            response = client.get(f'https://gate.ahram.org.eg/Search/{encoded_search}.aspx', 
                                  params=params, 
                                  headers=self.get_headers(),
                                  proxies=self.get_proxy())
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
