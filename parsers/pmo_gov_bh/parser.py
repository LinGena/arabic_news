import requests
import re
from datetime import datetime

from bs4 import BeautifulSoup

from parsers.model import CheckNewsModel
from utils.func import write_to_file_json


class NewsPmoGovBh(CheckNewsModel):
    def __init__(self, speaker: str):
        super().__init__()
        self.domain = 'https://www.pmo.gov.bh/'
        self.country = 'Bahrain'
        self.speaker = speaker
        self.filename_exception = 'parsers/pmo_gov_bh/exception_links.json'
        self.exception_links = self.get_exception_links(self.filename_exception)
        self.stop_parse_next = False

    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
                # Reset the flag for each new keyword
                self.stop_parse_next = False
                self.previous_page_links = set()
                self.current_page_links = set()
                page = 1
                current_html = None

                while True:
                    print(f'----- news_keyword = {news_keyword}, page = {page}')

                    # For the first page, use GET request
                    if page == 1:
                        current_html = self.get_response(news_keyword)
                    # For subsequent pages, use POST with ASP.NET postback
                    else:
                        current_html = self.get_next_page(news_keyword, current_html, page)

                    if current_html is None:
                        print(f"No more unique pages for keyword {news_keyword}")
                        break

                    links = self.get_links_from_search_news(current_html)
                    if not links:
                        print(f"No more links found for keyword {news_keyword}")
                        break
                    print(links)
                    self.get_links_content(links, news_keyword)

                    # Check if we've reached the last page
                    soup = BeautifulSoup(current_html, 'html.parser')
                    pagination = soup.select('.pagination li')
                    if pagination and 'disabled' in pagination[-1].get('class', []):
                        print(f"Reached last page for keyword {news_keyword}")
                        break

                    page += 1
        except Exception as ex:
            self.logger.error(ex)
            print(f"Error in get method: {ex}")
        finally:
            write_to_file_json(self.filename_exception, self.exception_links)

    def get_links_from_search_news(self, search_news: str) -> list:
        links = []
        soup = BeautifulSoup(search_news, 'html.parser')

        # The news items are in div elements with class "news-list"
        news_items = soup.find_all('div', class_='news-list')

        if not news_items:
            # Return None when no news items are found to indicate end of pagination
            return None

        no_results = soup.select_one('.no-results-message')
        if no_results:
            print("No results message found on page")
            return None

        # Keep track of found links to detect duplicate pages
        self.current_page_links = set()

        for item in news_items:
            h4_tag = item.find('h4')
            if h4_tag:
                a_tag = h4_tag.find('a')
                if a_tag and 'href' in a_tag.attrs:
                    link = a_tag.get('href')
                    if not link.startswith('http'):
                        link = self.domain + link
                    if not self.db_check_link(link, self.speaker):
                        links.append(link)
                    # Add to current page set regardless of if it's in DB
                    self.current_page_links.add(link)

        return links

    def get_links_content(self, links: list, search_keyword: str) -> None:
        for link in links:
            try:
                # Skip if already in database
                if self.db_check_link(link, self.speaker):
                    continue

                # Skip if in exception list
                if link in self.exception_links:
                    continue

                headers = self.get_headers()
                response = requests.get(link, headers=headers, proxies=self.get_proxy())
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract article title - try multiple selectors
                title = ""
                title_selectors = [
                    'h4.mb20',
                    'h2.pagetitle',
                    'h3.subpage_title',
                    '.pagetitle',
                    '.news-details h4'
                ]

                for selector in title_selectors:
                    title_element = soup.select_one(selector)
                    if title_element:
                        title = title_element.text.strip()
                        break

                # Extract article content - try multiple approaches
                content = ""

                # Try specific content containers
                content_selectors = [
                    '.section-whitebg',
                    '.news-details',
                    '.article-content',
                    '.entry-content'
                ]

                for selector in content_selectors:
                    content_element = soup.select_one(selector)
                    if content_element:
                        # Remove unwanted elements
                        for unwanted in content_element.select(
                                '.sharethis-link, .addthis_inline_share_toolbox, .date, h4'):
                            unwanted.decompose()

                        # Also remove the image caption and carousel
                        for unwanted in content_element.select('.news-carousel-wrap, .news-img-caption'):
                            unwanted.decompose()

                        content = content_element.get_text(strip=True, separator=' ')
                        break

                # Extract date from the date div
                news_date = None
                should_skip = False
                date_element = soup.select_one('.date')

                if date_element:
                    date_text = date_element.text.strip()
                    date_obj = self.parse_date(date_text)

                    if date_obj:
                        news_date = date_obj.strftime("%Y-%m-%d")
                        should_skip = date_obj < self.stop_date_create

                # If no date found in the page, try extracting from URL
                if not news_date:
                    # Try to get date from URL - YYYY-MM-DD format
                    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', link)
                    if date_match:
                        year, month, day = date_match.groups()
                        news_date = f"{year}-{month}-{day}"
                        date_obj = datetime.strptime(news_date, "%Y-%m-%d")
                        should_skip = date_obj < self.stop_date_create

                # Skip article if it's too old and add to exception list
                if should_skip:
                    if link not in self.exception_links:
                        self.exception_links.append(link)
                    continue

                # Create result dictionary
                res = self.get_result_dict(search_keyword, self.domain, link, self.speaker, self.country)
                res['news_title'] = self.clear_text(title)
                res['news_body'] = self.clear_text(content)
                res['news_date'] = news_date

                res.update(self.check_aws_bedrock(self.speaker, res))
                if res['is_about']:
                    res['speaker'] = self.speaker
                self.db_client.insert_row(res)

            except Exception as ex:
                self.logger.error(f"Error processing link {link}: {ex}")

    def parse_date(self, date_text: str) -> tuple:
        """Parse Arabic date text into YYYY-MM-DD format and determine if it's too old."""
        try:
            # Convert Arabic numerals to Western
            for ar, en in self.arabic_to_western().items():
                date_text = date_text.replace(ar, en)

            # Convert Arabic month names
            for ar_month, en_month in self.arabic_months_dict().items():
                if ar_month in date_text:
                    date_text = date_text.replace(ar_month, en_month)
                    break

            # Try different date formats
            for fmt in ["%d %B %Y", "%B %d, %Y", "%d-%m-%Y", "%d/%m/%Y"]:
                try:
                    date_obj = datetime.strptime(date_text, fmt)

                    # Check if date is too old
                    should_skip = date_obj < self.stop_date_create
                    if should_skip:
                        self.stop_parse_next = True

                    # Return both the formatted date and whether to skip
                    return date_obj.strftime("%Y-%m-%d"), should_skip
                except ValueError:
                    continue

            return None, False  # Return default values if no date format matched
        except Exception as ex:
            self.logger.error(f"Error parsing date {date_text}: {ex}")
            return None, False  # Return default values on exception

    def get_response(self, news_keyword: str, count_try: int = 0) -> str:
        """Get the first page of search results."""
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with response. News_keyword: {news_keyword}')

        try:
            headers = self.get_headers()
            url = f'https://www.pmo.gov.bh/search.aspx?search-input={news_keyword}'

            response = requests.get(url, headers=headers, proxies=self.get_proxy())
            response.raise_for_status()

            return response.text
        except Exception as ex:
            self.logger.error(f"Error getting first page for keyword {news_keyword}: {ex}")
        finally:
            if 'response' in locals() and isinstance(response, requests.Response):
                response.close()

        return self.get_response(news_keyword, count_try + 1)

    def get_next_page(self, news_keyword: str, current_html: str, page: int, count_try: int = 0) -> str:
        """Get the next page of search results using ASP.NET postback."""
        if hasattr(self, 'previous_page_links') and self.current_page_links == self.previous_page_links:
            return None

        # Store current page links for next comparison
        self.previous_page_links = self.current_page_links.copy()

        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with response. News_keyword: {news_keyword}, Page: {page}')

        try:
            headers = self.get_headers()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

            url = f'https://www.pmo.gov.bh/search.aspx?search-input={news_keyword}'

            # Extract form data from current page
            soup = BeautifulSoup(current_html, 'html.parser')

            # Find the pagination controls to determine what to click
            pagination = soup.select('.pagination a')
            if len(pagination) == 0:
                return None

            next_page_event = None

            # Look for the next page button or numbered page
            for a in pagination:
                # If we find a direct link to our target page number
                if a.text.strip() == str(page):
                    onclick = a.get('onclick', '')
                    if "__doPostBack" in onclick:
                        event_target = onclick.split("'")[1]
                        next_page_event = event_target
                        break

            # If we didn't find a direct page number, look for a "Next" button
            if not next_page_event:
                next_buttons = soup.select('.pagination li:last-child a')
                if not next_buttons:
                    return None

                next_button = next_buttons[0]  # Get the first element from the list
                if 'disabled' in next_button.get('class', []):
                    return None

                onclick = next_button.get('onclick', '')
                if "__doPostBack" in onclick:
                    event_target = onclick.split("'")[1]
                    next_page_event = event_target

            # If we still don't have an event target, use a default format
            if not next_page_event:
                next_page_event = f'ctl00$cphBaseBodySubPageContent$BootStrapDataPager1$ctl01$ctl0{page - 1}'

            # Get the hidden form fields
            data = {
                '__EVENTTARGET': next_page_event,
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': soup.select_one('#__VIEWSTATE')['value'],
                '__VIEWSTATEGENERATOR': soup.select_one('#__VIEWSTATEGENERATOR')['value'],
                '__EVENTVALIDATION': soup.select_one('#__EVENTVALIDATION')['value'],
                'ctl00$cphBaseBodySubPageContent$searchInput': news_keyword
            }

            response = requests.post(url, data=data, headers=headers, proxies=self.get_proxy())
            response.raise_for_status()

            return response.text
        except Exception as ex:
            self.logger.error(f"Error fetching page {page} for keyword {news_keyword}: {ex}")
        finally:
            if 'response' in locals() and isinstance(response, requests.Response):
                response.close()

        return self.get_next_page(news_keyword, current_html, page, count_try + 1)

    def get_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.pmo.gov.bh/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0"
        }