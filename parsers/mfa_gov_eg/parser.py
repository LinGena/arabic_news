import cloudscraper
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from parsers.model import CheckNewsModel
from utils.func import write_to_file_json
import requests
import re
import random
import time


class NewsMfaGovEg(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.mfa.gov.eg/'
        self.speaker = speaker
        self.country = 'Egypt'
        self.filename_exeption = 'parsers/mfa_gov_eg/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exeption)

    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
                page = 0
                self.logger.info(f"Processing keyword: {news_keyword}")
                search_news = self.get_response(news_keyword, page)
                links = self.get_links_from_search_news(search_news)

                if links is not None and links:
                    self.logger.info(f"Found {len(links)} links for keyword: {news_keyword}")
                    self.get_links_content(links, news_keyword)
                else:
                    self.logger.warning(f"No links found for keyword: {news_keyword}")

        except Exception as ex:
            self.logger.error(f"Error in main processing loop: {ex}")
        finally:
            write_to_file_json(self.filename_exeption, self.exception_links)

    def is_date_too_old(self, date_str: str) -> bool:
        """
        Check if a date string is older than the stop_date_create

        Args:
            date_str: Date string in YYYY-MM-DD format

        Returns:
            bool: True if date is too old, False otherwise
        """
        try:
            if not date_str:
                return True

            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return date_obj < self.stop_date_create
        except Exception as ex:
            self.logger.warning(f"Error checking date: {ex}, assuming date is too old")
            return True

    def validate_date(self, date_str: str) -> bool:
        """
        Validate that a date string is:
        1. In proper format
        2. Not in the far future
        3. Not too old (before stop_date_create)

        Args:
            date_str: Date string in YYYY-MM-DD format

        Returns:
            bool: True if date is valid, False otherwise
        """
        try:
            if not date_str:
                return False

            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            current_date = datetime.now()

            # Date can't be more than 7 days in the future (allowing for timezone differences)
            if date_obj > current_date.replace(day=current_date.day + 7):
                self.logger.warning(f"Date is in the far future: {date_str}")
                return False

            # Date can't be before stop_date_create
            if date_obj < self.stop_date_create:
                self.logger.info(f"Date is too old: {date_str}")
                return False

            # Make sure year is reasonable (not 1967, etc.)
            if date_obj.year < 2000:
                self.logger.warning(f"Date year too old: {date_str}")
                return False

            return True
        except Exception as ex:
            self.logger.warning(f"Error validating date: {ex}")
            return False

    def get_links_from_search_news(self, search_news: str) -> list:
        links = []
        soup = BeautifulSoup(search_news, 'html.parser')

        # Find all tab panes with search results
        tab_content = soup.find('div', id='pills-tabContent')
        if not tab_content:
            self.logger.warning("No tab content found in search results")
            return []

        # Find all tab panes (they have classes like "tab-pane fade show active")
        tab_panes = tab_content.find_all('div', class_='tab-pane')

        for tab_pane in tab_panes:
            # Find all news items in the row
            news_blocks = tab_pane.find_all('div', class_='col-xl-3 col-lg-4 col-md-6')

            if not news_blocks:
                continue

            for news_block in news_blocks:
                try:
                    # Each news item has an anchor tag with a link
                    a_tag = news_block.find('a')
                    if a_tag and a_tag.has_attr('href'):
                        link = a_tag.get('href')
                        # Handle relative URLs
                        if not link.startswith(('http://', 'https://')):
                            link = self.domain + link.lstrip('/')

                        # Check if this link has already been processed
                        if link in self.exception_links:
                            self.logger.debug(f"Skipping exception link: {link}")
                            continue

                        if self.db_check_link(link, self.speaker):
                            self.logger.debug(f"Skipping already processed link: {link}")
                            continue

                        # Try to extract date from URL if possible
                        date_match = re.search(r'/(\d{4})[/-](\d{1,2})[/-](\d{1,2})/', link)
                        if date_match:
                            year, month, day = date_match.groups()
                            try:
                                date_str = f"{year}-{int(month):02d}-{int(day):02d}"
                                if self.is_date_too_old(date_str):
                                    self.logger.info(f"Skipping link with old date in URL: {link}, date: {date_str}")
                                    continue
                            except Exception:
                                # If date parsing fails, we'll check the actual content later
                                pass

                        links.append(link)
                except Exception as ex:
                    self.logger.warning(f"Error processing search result item: {ex}")
                    continue

        return links

    def extract_date_from_content(self, soup: BeautifulSoup, news_body: str) -> tuple:
        """
        Extract date from content using multiple methods and validate it

        Args:
            soup: BeautifulSoup object of the page
            news_body: Extracted news body text

        Returns:
            tuple: (date_str, stop_parse) where date_str is in YYYY-MM-DD format and stop_parse is True if date is invalid
        """
        # Method 1: Try to find explicit date element
        date_element = soup.find('span', id='ContentMain_lblDate')
        if date_element:
            try:
                date, stop_parse = self.get_news_create(date_element)
                if date and not stop_parse:
                    if self.validate_date(date):
                        return date, False
                    else:
                        return "", True
            except Exception as ex:
                self.logger.debug(f"Error parsing explicit date element: {ex}")

        # Method 2: Look for meta tags
        meta_date = None
        for meta in soup.find_all('meta'):
            if meta.get('name') in ['date', 'pubdate', 'publication_date', 'article:published_time']:
                meta_date = meta.get('content')
                if meta_date:
                    try:
                        # Try to parse ISO format date
                        date_obj = datetime.fromisoformat(meta_date.replace('Z', '+00:00'))
                        date = date_obj.strftime("%Y-%m-%d")
                        if self.validate_date(date):
                            return date, False
                    except Exception:
                        pass

        # Method 3: Try to extract date from the content using regex patterns
        date_patterns = [
            # Format: day month year (with Arabic or Western numerals)
            r'(\d+)\s+(يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر)\s+(\d{4})',
            r'([\u0660-\u0669]+)\s+(يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر)\s+([\u0660-\u0669]{4})',

            # Format: day monthname year with specific day names (Thursday, etc.)
            r'(الخميس|الجمعة|السبت|الأحد|الاثنين|الثلاثاء|الأربعاء)\s+(\d+)\s+(يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر)\s+(\d{4})',
            r'يوم\s+(الخميس|الجمعة|السبت|الأحد|الاثنين|الثلاثاء|الأربعاء)\s+(\d+)\s+(يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر)\s+(\d{4})',

            # Format for dates with Arabic numerals and different month naming
            r'([\u0660-\u0669]+)\s+(كانون الثاني|شباط|آذار|نيسان|أيار|حزيران|تموز|آب|أيلول|تشرين الأول|تشرين الثاني|كانون الأول)\s+([\u0660-\u0669]{4})'
        ]

        # Prioritize dates in the first 500 characters (more likely to be publication date)
        # and avoid dates in quotes which are often historical references
        first_content = news_body[:500]
        for pattern in date_patterns:
            match = re.search(pattern, first_content)
            if match:
                try:
                    groups = match.groups()
                    # Handle different pattern formats
                    if len(groups) == 3:
                        day, month_arabic, year = groups
                    elif len(groups) == 4:
                        if 'يوم' in pattern:
                            _, day, month_arabic, year = groups
                        else:
                            day, month_arabic, year = groups[1:]

                    # Convert Arabic numerals if needed
                    if day and ord(day[0]) >= 0x0660 and ord(day[0]) <= 0x0669:
                        arabic_to_western = self.arabic_to_western()
                        day = ''.join([arabic_to_western.get(c, c) for c in day])
                        year = ''.join([arabic_to_western.get(c, c) for c in year])

                    # Convert month name to English
                    if 'كانون' in month_arabic or 'شباط' in month_arabic or 'آذار' in month_arabic:
                        month_dict = self.arabic_months_dict_second()
                    else:
                        month_dict = self.arabic_months_dict()

                    month = month_dict.get(month_arabic)

                    if month:
                        date_obj = datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
                        date = date_obj.strftime("%Y-%m-%d")
                        if self.validate_date(date):
                            return date, False
                except Exception as ex:
                    self.logger.debug(f"Error parsing content date: {ex}")

        # Method 4: Look for YYYY-MM-DD format in content
        date_match = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', news_body)
        if date_match:
            try:
                year, month, day = date_match.groups()
                date = f"{year}-{int(month):02d}-{int(day):02d}"
                if self.validate_date(date):
                    return date, False
            except Exception as ex:
                self.logger.debug(f"Error parsing YYYY-MM-DD date: {ex}")

        # No valid date found
        return "", True

    def get_links_content(self, links: list, search_keyword: str) -> None:
        """
        Process a list of links to extract news content from the Egyptian Ministry of Foreign Affairs website.

        Args:
            links: List of URLs to process
            search_keyword: Keyword used for searching
        """
        for link in links:
            try:
                if link in self.exception_links:
                    self.logger.info(f"Skipping already processed exception link: {link}")
                    continue

                self.logger.info(f"Processing link: {link}")
                page_content = self.news_content_response(link)

                if not page_content:
                    self.logger.warning(f"Empty content received for link: {link}")
                    self.exception_links.append(link)
                    continue

                soup = BeautifulSoup(page_content, 'html.parser')

                # Extract news title - handle different page structures
                title_element = soup.find('h2', class_='about-title')
                if not title_element:
                    title_element = soup.find('span', id='ContentMain_lblContentTitle')

                if not title_element:
                    self.logger.warning(f"No title found for link: {link}")
                    self.exception_links.append(link)
                    continue

                news_title = self.clear_text(title_element.get_text())

                # Extract news body - handle different page structures
                news_body = ""

                # Try to find body in span.mt-20 with paragraphs (common structure)
                body_container = soup.find('span', class_='mt-20')
                if body_container:
                    paragraphs = body_container.find_all('p')
                    if paragraphs:
                        news_body = " ".join([self.clear_text(p.get_text()) for p in paragraphs])
                    else:
                        news_body = self.clear_text(body_container.get_text())

                # Try alternate structure (ContentMain_lblBody)
                if not news_body:
                    body_element = soup.find('span', id='ContentMain_lblBody')
                    if body_element:
                        news_body = self.clear_text(body_element.get_text())

                # Try alternate structure (width-for-news)
                if not news_body:
                    news_container = soup.find('div', class_='width-for-news')
                    if news_container:
                        # Look for text in paragraphs or direct text
                        paragraphs = news_container.find_all('p')
                        if paragraphs:
                            news_body = " ".join([self.clear_text(p.get_text()) for p in paragraphs])
                        else:
                            # Get text excluding titles
                            for element in news_container.find_all(text=True, recursive=True):
                                if element.parent.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                                    news_body += " " + element.strip()
                            news_body = self.clear_text(news_body)

                if not news_body:
                    self.logger.warning(f"No content body found for link: {link}")
                    self.exception_links.append(link)
                    continue

                # Extract and validate date
                date, stop_parse = self.extract_date_from_content(soup, news_body)

                if not date or stop_parse:
                    self.logger.info(f"Date too old or not found for link: {link}, date: {date}")
                    self.exception_links.append(link)
                    continue

                # Create result dictionary
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                res['news_title'] = news_title
                res['news_body'] = news_body
                res['news_date'] = date

                # Check with AWS Bedrock for relevance
                bedrock_result = self.check_aws_bedrock(self.speaker, res)
                res.update(bedrock_result)

                # Insert to database
                self.db_client.insert_row(res)
                self.logger.info(f"Successfully processed: {news_title[:50]}... (Date: {date})")

            except Exception as ex:
                self.logger.error(f"{ex}, link: {link}")
                if link not in self.exception_links:
                    self.exception_links.append(link)

    def get_news_create(self, createdby: BeautifulSoup) -> tuple:
        if not createdby:
            return '', True

        try:
            arabic_date = createdby.get_text().strip()
            arabic_months_dict = self.arabic_months_dict_second()
            parts = arabic_date.split()

            if len(parts) > 3:
                day = parts[0]
                arabic_month = parts[1] + ' ' + parts[2]
                year = parts[3]
            else:
                day, arabic_month, year = parts

            month = arabic_months_dict.get(arabic_month)
            if not month:
                return '', True

            # Convert Arabic numerals if needed
            if ord(day[0]) >= 0x0660 and ord(day[0]) <= 0x0669:
                arabic_to_western = self.arabic_to_western()
                day = ''.join([arabic_to_western.get(c, c) for c in day])
                year = ''.join([arabic_to_western.get(c, c) for c in year])

            date_obj = datetime.strptime(f"{day} {month} {year}", "%d %B %Y")

            # Extra validation to avoid extremely old dates
            if date_obj.year < 2000:
                return '', True

            stop_parse = date_obj < self.stop_date_create
            return date_obj.strftime("%Y-%m-%d"), stop_parse

        except Exception as ex:
            self.logger.warning(f"Error parsing date: {ex}")
            return '', True

    def news_content_response(self, link: str, count_try: int = 0) -> str:
        """
        Get the content of a news page with improved error handling and retry logic.

        Args:
            link: URL to fetch
            count_try: Current retry attempt count

        Returns:
            str: HTML content of the page

        Raises:
            Exception: If maximum retry attempts are exceeded
        """
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with news content. Link: {link}')

        try:
            # Method 1: Simple requests with SSL verification disabled
            try:
                response = requests.get(
                    link,
                    verify=False,
                    headers=self.get_headers(),
                    timeout=30
                )
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                self.logger.debug(f"Simple request failed: {str(e)[:100]}...")

            # Method 2: Try with cloudscraper and proxy
            try:
                client = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'mobile': False
                    }
                )
                client.verify = False  # Disable SSL verification

                response = client.get(
                    link,
                    proxies=self.get_proxy(),
                    headers=self.get_headers(),
                    timeout=30
                )
                response.raise_for_status()
                return response.text
            except Exception as e:
                self.logger.debug(f"Cloudscraper with proxy failed: {str(e)[:100]}...")
            finally:
                if 'client' in locals():
                    client.close()

            # Method 3: Try with requests session
            try:
                session = requests.Session()
                session.verify = False
                session.headers.update(self.get_headers())

                response = session.get(link, timeout=45)
                response.raise_for_status()
                return response.text
            except Exception as e:
                self.logger.debug(f"Session request failed: {str(e)[:100]}...")
                raise

        except Exception as ex:
            self.logger.warning(f"All request methods failed for {link}: {str(ex)[:100]}...")

            # Implement exponential backoff with jitter
            backoff = min(30, 2 ** count_try) + random.uniform(0, 1)
            self.logger.info(f"Retrying in {backoff:.2f} seconds (attempt {count_try + 1}/{self.max_count_try})...")
            time.sleep(backoff)

        return self.news_content_response(link, count_try + 1)

    def get_response(self, news_keyword: str, page: int = 1, count_try: int = 0) -> str:
        """
        Get search results with improved proxy handling and SSL verification bypass.
        """
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with response. News_keyword: {news_keyword}, Page: {page}')

        encoded_search = urllib.parse.quote(news_keyword)
        search_url = f'https://www.mfa.gov.eg/ar/Search?search={encoded_search}'

        try:
            # Method 1: Direct request without proxy - simplest approach
            try:
                # Disable SSL verification warnings
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

                response = requests.get(
                    search_url,
                    verify=False,
                    headers=self.get_headers(),
                    timeout=30
                )
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                self.logger.debug(f"Direct request failed: {str(e)[:100]}...")

            # Method 2: Try with cloudscraper and explicit proxy formatting
            try:
                client = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'mobile': False
                    }
                )
                client.verify = False

                # Get a proxy string that already contains auth credentials
                proxy_str = random.choice(self.proxies_list)
                proxies = {
                    'http': proxy_str,
                    'https': proxy_str
                }

                response = client.get(
                    search_url,
                    proxies=proxies,
                    headers=self.get_headers(),
                    timeout=30
                )
                response.raise_for_status()
                return response.text
            except Exception as e:
                self.logger.debug(f"Cloudscraper with proxy failed: {str(e)[:100]}...")
            finally:
                if 'client' in locals():
                    client.close()

            # Method 3: Try with requests session and session-level proxy
            try:
                session = requests.Session()
                session.verify = False
                session.headers.update(self.get_headers())

                # Get a different proxy
                proxy_str = random.choice(self.proxies_list)
                session.proxies = {
                    'http': proxy_str,
                    'https': proxy_str
                }

                response = session.get(search_url, timeout=45)
                response.raise_for_status()
                return response.text
            except Exception as e:
                self.logger.debug(f"Session request failed: {str(e)[:100]}...")
                raise

        except Exception as ex:
            self.logger.warning(f"All request methods failed for {search_url}: {str(ex)[:100]}...")

            # Implement exponential backoff
            backoff = min(30, 2 ** count_try) + random.uniform(0, 1)
            self.logger.info(f"Retrying in {backoff:.2f} seconds (attempt {count_try + 1}/{self.max_count_try})...")
            time.sleep(backoff)

        return self.get_response(news_keyword, page, count_try + 1)

    def get_headers(self) -> dict:
        """
        Get request headers with rotating user agents to avoid blocking.
        """
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        ]

        return {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5,ar;q=0.3",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
            "Referer": "https://www.google.com/"
        }