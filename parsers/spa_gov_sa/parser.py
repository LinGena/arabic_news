import requests
from datetime import datetime
from parsers.model import CheckNewsModel


class NewsSpaGovSa(CheckNewsModel):
    def __init__(self, speakers: list[str]):
        super().__init__()
        self.domain = 'https://www.spa.gov.sa/'
        self.country = 'Saudi Arabia'
        self.speakers = speakers
        
    def get(self) -> None:
        try:
            for news_keyword in self.get_search_terms():
                self.stop_parse_next = False
                page = 1
                while not self.stop_parse_next:
                    search_news = self.get_response(news_keyword, page)
                    if not search_news:
                        break
                    self.get_links_content(search_news, news_keyword)
                    page += 10
        except Exception as ex:
            self.logger.error(ex)
    
    def get_links_content(self, links: list[dict], search_keyword: str) -> None:
        for link in links:
            try:
                link_news = self.domain + link['uuid']
                i = 1
                if self.stop_parse_next:
                    break
                for speaker in self.speakers:
                    str_speakers = ', '.join(self.speakers)
                    if self.db_check_link(link_news, str_speakers) or self.db_check_link(link_news, speaker):
                        continue
                    res = self.get_result_dict(search_keyword, self.domain, link_news, str_speakers, self.country)
                    res['news_title']=link.get('title')
                    res['news_body']=link.get('content')
                    res['news_date']=self.get_news_create(link.get('published_at'))
                    if self.stop_parse_next:
                        break
                    res.update(self.check_aws_bedrock(speaker, res))
                    if res['is_about'] or i == 1:
                        if res['is_about']:
                            res['speaker'] = speaker
                        self.db_client.insert_row(res)
                    i+=1
            except Exception as ex:
                self.logger.error(ex)
    
    def get_news_create(self, timestamp: int) -> str:
        if not timestamp:
            self.stop_parse_next = True
            return
        date_obj = datetime.fromtimestamp(timestamp)
        if date_obj < self.stop_date_create:
            self.stop_parse_next = True
        return date_obj.strftime("%Y-%m-%d")

    def get_response(self, news_keyword: str, page: int = 1, count_try: int = 0) -> str:
        if count_try > self.max_count_try:
            raise Exception(f'Something wrong with bna_response. News_keyword: {news_keyword}, Page: {page}')
        try:
            headers = self.get_headers()
            params = {
                'title': f'{news_keyword}',
                'exact_search': '1',
                'by_latest': '1',
                'start': f'{page}',
                'rows': '10',
                'l': 'ar',
            }
            response = requests.get('https://portalapi.spa.gov.sa/api/v1/news/search',
                params=params, 
                headers=headers,
                proxies=self.get_proxy())
            response.raise_for_status()
            data : dict = response.json()
            return data.get('data',[])
        except Exception as ex:
            # print(ex)
            pass
        finally:
            if 'response' in locals() and isinstance(response, requests.Response):
                response.close()
        return self.get_response(news_keyword, page, count_try + 1)
    
    def get_headers(self) -> dict:
        return {
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
                "Connection": "keep-alive",
            } 