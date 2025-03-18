from http.client import responses

import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json
import ssl
import requests
import urllib3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context


class NewsCrownprinceBh(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.crownprince.bh'
        self.speaker = speaker
        self.country = 'Bahrain'
        self.filename_exeption = 'parsers/crownprince_bh/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)
        self.all_seen_links = set()

    def get(self) -> None:
        try:
            self.all_seen_links = set()

            for news_keyword in self.get_search_terms():
                page = 0
                self.parse_next = True
                while self.parse_next:
                    print('---- page:', page, 'keyword:', news_keyword)
                    search_news = self.get_response(news_keyword, page)
                    links = self.get_links_from_search_news(search_news)
                    if links:
                        self.get_links_content(links, news_keyword)
                    page += 1
        except Exception as ex:
            self.logger.error(ex)
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def get_links_from_search_news(self, response_text: str) -> list:
        """
        Extract links and dates from the Crown Prince website search results.
        Maintains a class-level set of all seen links to prevent duplication across iterations.

        Args:
            response_text: Raw HTML response text from the search

        Returns:
            List of dictionaries with links and dates
        """
        from bs4 import BeautifulSoup

        links = []
        links_set = set()

        if "___ASPSTART_HTML___" in response_text and "___ASPEND_HTML___" in response_text:
            html_start = response_text.find("___ASPSTART_HTML___") + len("___ASPSTART_HTML___")
            html_end = response_text.find("___ASPEND_HTML___")
            html_content = response_text[html_start:html_end]
        else:
            html_content = response_text

        soup = BeautifulSoup(html_content, 'html.parser')

        items = soup.find_all('div', class_='item')

        if not items:
            self.parse_next = False
            return []

        for item in items:
            date_elem = item.find('span', class_='asp_date')
            if date_elem:
                date = date_elem.text.strip()
            else:
                date = None

            if hasattr(self, 'check_date') and date and not self.check_date(date):
                continue

            link_elem = item.find('a', class_='asp_res_url')
            if link_elem and 'href' in link_elem.attrs:
                link = link_elem['href']

                if link in links_set or link in self.all_seen_links:
                    continue

                links_set.add(link)
                self.all_seen_links.add(link)

                if hasattr(self, 'db_check_link') and self.db_check_link(link, getattr(self, 'speaker', None)):
                    continue

                result = {
                    'link': link,
                    'date': date
                }

                links.append(result)

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
                news_title_block = soup.find('h1')
                if news_title_block:
                    news_title = news_title_block.get_text()
                res['news_title'] = self.clear_text(news_title)
                res['news_body'] = self.clear_text(full_text)
                res['news_date'] = data['date']
                print(res)
                res.update(self.check_aws_bedrock(self.speaker, res))
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
            response = requests.get(link, proxies=self.get_proxy(), headers=self.get_headers(), verify=False)
            response.raise_for_status()
            return response.text
        except Exception as ex:
            print(ex)
            pass
        finally:
            client.close()
        return self.news_content_response(link, count_try + 1)

    def get_response(self, news_keyword: str, page: int = 1, count_try: int = 0) -> str:
        """
        Alternative implementation using the requests library directly
        instead of cloudscraper, in case the SSL issues persist.
        """
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with bna_response. News_keyword: {news_keyword}, Page: {page}')
        try:
            import requests
            from requests.packages.urllib3.exceptions import InsecureRequestWarning

            # Suppress only the specific InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

            cookies = {
                'wp-wpml_current_language': 'ar',
            }

            data = {
                'action': 'ajaxsearchpro_search',
                'aspp': news_keyword,
                'asid': '1',
                'asp_inst_id': '1_1',
                'options': f'filters_initial=1&filters_changed=0&wpml_lang=ar&qtranslate_lang=0&current_page_id=2',
                'asp_call_num': page
            }

            session = requests.Session()

            response = session.post(
                'https://www.crownprince.bh/user-ajax.php',
                data=data,
                headers=self.get_headers(),
                cookies=cookies,
                proxies=self.get_proxy(),
                verify=False,
                timeout=30
            )

            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return response.text

        except Exception as ex:
            print(f"Error: {ex}")
            import time
            time.sleep(2)
            return self.get_response(news_keyword, page, count_try + 1)
        finally:
            if 'session' in locals():
                session.close()

    def get_headers(self) -> dict:
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.crownprince.bh',
            'Referer': 'https://www.crownprince.bh/',
            'X-Requested-With': 'XMLHttpRequest'
        }
