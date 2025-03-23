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
                try:
                    page = 0
                    self.parse_next = True
                    consecutive_empty_pages = 0
                    max_empty_pages = 3  # Stop after 3 consecutive empty pages

                    while self.parse_next and consecutive_empty_pages < max_empty_pages:
                        self.logger.info(f'---- page: {page}, keyword: {news_keyword}')
                        search_news = self.get_response(news_keyword, page)

                        if not search_news:
                            self.logger.warning(f"Empty response for keyword '{news_keyword}' on page {page}")
                            consecutive_empty_pages += 1
                            page += 1
                            continue

                        links = self.get_links_from_search_news(search_news)

                        if not links:
                            consecutive_empty_pages += 1
                            self.logger.info(
                                f"No valid links found for keyword '{news_keyword}' on page {page}, empty page count: {consecutive_empty_pages}")
                        else:
                            consecutive_empty_pages = 0  # Reset counter when we find links
                            self.logger.info(f"Found {len(links)} links for keyword '{news_keyword}' on page {page}")
                            self.get_links_content(links, news_keyword)

                        page += 1

                    if consecutive_empty_pages >= max_empty_pages:
                        self.logger.info(
                            f"Stopping after {consecutive_empty_pages} consecutive empty pages for keyword '{news_keyword}'")

                except Exception as keyword_ex:
                    self.logger.error(f"Error processing keyword '{news_keyword}': {keyword_ex}")
                    # Continue with next keyword instead of stopping completely
                    continue

        except Exception as ex:
            self.logger.error(f"Critical error in main processing loop: {ex}")
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def convert_arabic_date_to_iso(self, arabic_date: str) -> str:
        """
        Convert Arabic date format to ISO format (YYYY-MM-DD)

        Args:
            arabic_date: Date in Arabic format (e.g. "3 أغسطس 2014")

        Returns:
            Date in ISO format (e.g. "2014-08-03") or None if conversion fails
        """
        try:
            # First, convert any Arabic numerals to Western numerals
            for ar, en in self.arabic_to_western().items():
                arabic_date = arabic_date.replace(ar, en)

            # Split the date into parts
            parts = arabic_date.split()
            if len(parts) != 3:
                self.logger.warning(f"Unexpected date format: {arabic_date}")
                return None

            day = parts[0].zfill(2)  # Pad with leading zero if needed

            # Try both Arabic month dictionaries
            month_name = parts[1]
            month_en = self.arabic_months_dict().get(month_name)

            if not month_en:
                month_en = self.arabic_months_dict_second().get(month_name)

            if not month_en:
                self.logger.warning(f"Unknown month: {month_name} in date {arabic_date}")
                return None

            year = parts[2]

            # Convert to datetime for validation and formatting
            date_obj = datetime.strptime(f"{day} {month_en} {year}", "%d %B %Y")
            return date_obj.strftime("%Y-%m-%d")
        except Exception as ex:
            # Log the error and return None
            self.logger.error(f"Error converting date '{arabic_date}': {ex}")
            return None

    def check_date(self, date_str: str) -> bool:
        """
        Check if the date is within the acceptable range
        Returns True if the date should be processed, False otherwise
        """
        try:
            # Convert Arabic date to ISO format
            iso_date = self.convert_arabic_date_to_iso(date_str)
            if not iso_date:
                return False

            # Parse the ISO date
            date_obj = datetime.strptime(iso_date, "%Y-%m-%d")

            # Check if the date is newer than the stop date
            return date_obj >= self.stop_date_create
        except Exception as ex:
            self.logger.error(f"Date check error: {ex} for date: {date_str}")
            return False

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
                # Skip items without dates
                continue

            link_elem = item.find('a', class_='asp_res_url')

            # Check if date is in the acceptable range
            if not self.check_date(date):
                # Old date detected, add to exception list
                if link_elem and 'href' in link_elem.attrs:
                    old_link = link_elem['href']
                    if old_link not in self.exception_links:
                        self.exception_links.append(old_link)
                        self.logger.info(f"Adding old link to exceptions (date: {date}): {old_link}")
                continue

            if link_elem and 'href' in link_elem.attrs:
                link = link_elem['href']

                if link in links_set or link in self.all_seen_links:
                    continue

                links_set.add(link)
                self.all_seen_links.add(link)

                # Check if the link has already been processed in previous runs
                if self.db_check_link(link, self.speaker):
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

                # Convert the Arabic date to ISO format
                arabic_date = data['date']
                iso_date = self.convert_arabic_date_to_iso(arabic_date)
                if not iso_date:
                    # Skip entries where date conversion fails instead of using a placeholder
                    self.logger.warning(f"Skipping link due to date conversion failure: {link}, date: {arabic_date}")
                    continue

                res['news_date'] = iso_date

                print(res)
                # Update with AWS Bedrock check and handle possible errors
                try:
                    bedrock_result = self.check_aws_bedrock(self.speaker, res)
                    res.update(bedrock_result)
                except Exception as bedrock_ex:
                    self.logger.error(f"AWS Bedrock error: {bedrock_ex}, link: {link}")
                    res.update({'is_about': False, 'explanation': 'Error in AWS Bedrock processing'})

                self.db_client.insert_row(res)
            except Exception as ex:
                self.logger.error(f'{ex}, link: {link}')
                # Add the failed link to exception_links to avoid retrying
                if link not in self.exception_links:
                    self.exception_links.append(link)

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
            self.logger.error(f'Maximum retries exceeded for news content. Link: {link}')
            return None

        try:
            # Try direct connection first if proxies are causing issues
            use_proxy = count_try < self.max_count_try // 2
            proxies = self.get_proxy() if use_proxy else None

            if not use_proxy:
                self.logger.info(f"Attempting direct connection without proxy after {count_try} failed attempts")

            # Use requests directly for consistency instead of mixing with cloudscraper
            response = requests.get(
                link,
                proxies=proxies,
                headers=self.get_headers(),
                verify=False,
                timeout=30
            )
            response.raise_for_status()
            return response.text

        except Exception as ex:
            # Log different types of errors differently
            if "ProxyError" in str(ex):
                self.logger.warning(f"Proxy error on attempt {count_try + 1}: {ex}")
            elif "ConnectionError" in str(ex) or "Connection refused" in str(ex):
                self.logger.warning(f"Connection error on attempt {count_try + 1}: {ex}")
            elif "Timeout" in str(ex):
                self.logger.warning(f"Timeout error on attempt {count_try + 1}: {ex}")
            else:
                self.logger.warning(f"Error on attempt {count_try + 1}: {ex}")

            # Increase backoff time with each retry
            import time
            backoff_time = 2 * (count_try + 1)  # Progressive backoff
            time.sleep(backoff_time)

        return self.news_content_response(link, count_try + 1)

    def get_response(self, news_keyword: str, page: int = 1, count_try: int = 0) -> str:
        """
        Alternative implementation using the requests library directly
        instead of cloudscraper, in case the SSL issues persist.
        """
        if count_try > self.max_count_try:
            self.logger.error(f'Maximum retries exceeded. Keywords: {news_keyword}, Page: {page}')
            return ""  # Return empty string instead of raising exception to continue with other keywords

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

            # Try direct connection first if proxies are causing issues
            use_proxy = count_try < self.max_count_try // 2
            proxies = self.get_proxy() if use_proxy else None

            if not use_proxy:
                self.logger.info(f"Attempting direct connection without proxy after {count_try} failed attempts")

            session = requests.Session()

            response = session.post(
                'https://www.crownprince.bh/user-ajax.php',
                data=data,
                headers=self.get_headers(),
                cookies=cookies,
                proxies=proxies,
                verify=False,
                timeout=30
            )

            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return response.text

        except Exception as ex:
            # Log different types of errors differently
            if "ProxyError" in str(ex):
                self.logger.warning(f"Proxy error on attempt {count_try + 1}: {ex}")
            elif "ConnectionError" in str(ex) or "Connection refused" in str(ex):
                self.logger.warning(f"Connection error on attempt {count_try + 1}: {ex}")
            elif "Timeout" in str(ex):
                self.logger.warning(f"Timeout error on attempt {count_try + 1}: {ex}")
            else:
                self.logger.error(f"Error on attempt {count_try + 1}: {ex}")

            # Increase backoff time with each retry
            import time
            backoff_time = 2 * (count_try + 1)  # Progressive backoff
            self.logger.info(f"Waiting {backoff_time} seconds before retry")
            time.sleep(backoff_time)

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