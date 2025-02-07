import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsUaeunOrg(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://uaeun.org/ar/'
        self.speaker = speaker
        self.country = 'United Arab Emirates'
        self.filename_exeption = 'parsers/uaeun_org/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
                page = 0
                self.parse_next = True
                while self.parse_next:
                    print('---- page:',page,'keyword:',news_keyword)
                    search_news = self.get_response(news_keyword, page)
                    links = self.get_links_from_search_news(search_news)
                    if links:
                        self.get_links_content(links, news_keyword)
                    page += 1
        except Exception as ex:
            self.logger.error(ex)
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def get_links_from_search_news(self, search_news: dict) -> list:
        links = []
        links_set = set()
        soup = BeautifulSoup(search_news["items"], 'html.parser')
        titles = soup.find_all('div', class_='event-card-item')
        if not titles:
            self.parse_next = False
            return None
        for title in titles:
            date, stop_parse = self.get_news_create(title.find('time'))
            if stop_parse:
                continue
            a_tegs = title.find_all('a')
            for a_teg in a_tegs:
                if self.domain in a_teg.get('href'):
                    link = a_teg.get('href')
                    if link not in links_set:
                        links_set.add(link)
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
                if not page_content:
                    continue
                soup = BeautifulSoup(page_content, 'html.parser')
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                text_list = [p.get_text(strip=True) for p in soup.find_all("p")]
                full_text = " ".join(text_list)
                news_title = ''
                news_title_block = soup.find('h2')
                if news_title_block:
                    news_title = news_title_block.get_text()
                res['news_title']=self.clear_text(news_title)
                res['news_body']=self.clear_text(full_text)
                res['news_date']=data['date']
                res['is_about']=self.check_aws_bedrock(self.speaker, res)
                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(f'{ex}, link: {link}')
    
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
            print(f'Something wrong with news content. Link: {link}')
            return None
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
            cookies = {
                'wp-wpml_current_language': 'ar',
            }
            params = {
                'action': 'contentmachine',
                'page': f'{page}',
                'post_type': 'statement',
                'pillars': 'all',
                'focus': 'all',
                'count': '9',
                'type': 'search',
                'search': f'{news_keyword}',
                'month': 'all',
                'year': 'all',
            }
            response = client.get('https://uaeun.org/wp/wp-admin/admin-ajax.php', 
                                  params=params, 
                                  cookies=cookies,
                                  proxies=self.get_proxy())
            response.raise_for_status()
            return response.json()
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
