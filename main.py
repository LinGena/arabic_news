import schedule
from dotenv import load_dotenv
from utils.func import *
import warnings
from parsers.bna_bh.parser import NewsBnaBh
from parsers.mofa_gov_bh.parser import NewsMofaGovBh
from parsers.presidency_eg.parser import NewsPresidencyEg
from parsers.egypttoday_com.parser import NewsEgypttoday
from parsers.gate_ahram_org_eg.parser import NewsGateAhramOrgEg
from parsers.kingabdullah_jo.parser import NewsKingabdullahJo
from parsers.mfa_gov_jo.parser import NewsMfaGovJo
from parsers.jordantimes_com.parser import NewsJordantimesCom
from parsers.spa_gov_sa.parser import NewsSpaGovSa
from parsers.mofa_gov_sa.parser import NewsMofaGovSa
from parsers.diwan_gov_qa.parser import NewsDiwanGovQa
from parsers.mofa_gov_qa.parser import NewsMofaGovQa
from parsers.ny_mission_qa.parser import NewsNyMissionQa
from parsers.mohamedbinzayed_ae.parser import NewsMohamedbinzayedAe
from parsers.mofa_gov_ae.parser import NewsMofaGovAe
from parsers.uaeun_org.parser import NewsUaeunOrg
from parsers.uae_embassy_org.parser import NewsUaeEmbassyOrg
from parsers.mfa_gov_eg.parser import NewsMfaGovEg


warnings.filterwarnings('ignore', message='Unverified HTTPS request')
load_dotenv(override=True)


def parse_bna():
    speaker = 'حمد بن عيسى آل خليفة'
    NewsBnaBh(speaker).get()

def parse_mofa_gov_bh():
    speakers = ['عبد اللطيف الزياني','جمال فارس الرويعي']
    NewsMofaGovBh(speakers).get()

def parse_presidency():
    speaker = 'عبد الفتاح سعيد حسين خليل السيسى'
    NewsPresidencyEg(speaker).get()

def parse_egypttoday():
    speaker = 'Badr Abdelatty'
    NewsEgypttoday(speaker).get()

def parse_gate_ahram_org_eg():
    speaker = 'أسامة عبد الخالق'
    NewsGateAhramOrgEg(speaker).get()

def parse_kingabdullah_jo():
    speaker = 'عبد الله الثاني بن الحسين'
    NewsKingabdullahJo(speaker).get()

def parse_mfa_gov_jo():
    # на этом сайте не работает пагинация в поиске
    speaker = 'ايمن حسين الصفدي'
    NewsMfaGovJo(speaker).get()
    
def parse_jordantimes_com():
    speaker = 'Mahmoud Daifallah Hmoud'
    NewsJordantimesCom(speaker).get()

def parse_spa_gov_sa():
    speakers = ['سلمان بن عبد العزیز آل سعود','محمد بن سلمان آل سعود','عبدالعزيز الواصل']
    NewsSpaGovSa(speakers).get()

def parse_mofa_gov_sa():
    # тут вообще поиск не работает, по statements проверяю
    speaker = 'فيصل بن فرحان آل سعود'
    NewsMofaGovSa(speaker).get()

def parser_diwan_gov_qa():
    speaker = 'تميم بن حمد بن خليفة آل ثاني'
    NewsDiwanGovQa(speaker).get()

def parse_mofa_gov_qa():
    speaker = 'محمد بن عبد الرحمن بن جاسم آل ثاني'
    NewsMofaGovQa(speaker).get()

def parse_ny_mission_qa():
    speaker = 'علياء بنت أحمد بن سيف آل ثاني'
    NewsNyMissionQa(speaker).get()

def parse_mohamedbinzayed_ae():
    speaker = 'محمد بن زايد آل نهيان'
    NewsMohamedbinzayedAe(speaker).get()

def parse_mofa_gov_ae():
    # тут на английском, потому что на арабском ничего не ищет по сайту
    speaker = 'Abdullah bin Zayed Al Nahyan'
    NewsMofaGovAe(speaker).get()

def parse_uaeun_org():
    speaker = 'محمد أبوشهاب'
    NewsUaeunOrg(speaker).get()

def parse_uae_embassy_org():
    # абсолютно не понятно что тут можно найти ?
    speaker = 'Yousef Al Otaiba'
    # NewsUaeEmbassyOrg(speaker).get()

def parse_mfa_gov_eg():
    speaker = 'بدر عبد العاطي'
    NewsMfaGovEg(speaker).get()

def main():
    functions = [
        parse_bna,
        parse_mofa_gov_bh,
        parse_presidency,
        parse_egypttoday,
        parse_gate_ahram_org_eg,
        parse_kingabdullah_jo,
        parse_mfa_gov_jo,
        parse_jordantimes_com,
        parse_spa_gov_sa,
        parse_mofa_gov_sa,
        parser_diwan_gov_qa,
        parse_mofa_gov_qa,
        parse_ny_mission_qa,
        parse_mohamedbinzayed_ae,
        parse_mofa_gov_ae,
        parse_uaeun_org,
        parse_uae_embassy_org,
        parse_mfa_gov_eg,

    ]
    for func in functions:
        try:
            print(f'Start {func.__name__}')
            func()
        except Exception as e:
            print(f"Error in {func.__name__}: {e}\n")


if __name__ == "__main__":
    # parse_bna()
    # parse_mofa_gov_bh()
    # parse_presidency()
    # parse_egypttoday()
    # parse_gate_ahram_org_eg()
    # parse_kingabdullah_jo()
    # parse_mfa_gov_jo()
    # parse_jordantimes_com()
    # parse_spa_gov_sa()
    # parse_mofa_gov_sa()
    # parser_diwan_gov_qa()
    # parse_mofa_gov_qa()
    # parse_ny_mission_qa()
    # parse_mohamedbinzayed_ae()
    # parse_mofa_gov_ae()
    # parse_uaeun_org()
    # parse_uae_embassy_org()
    main()
    schedule.every(1).day.do(main)
    while True:
        schedule.run_pending()

  