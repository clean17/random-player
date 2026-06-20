import aiohttp
import re, os, sys, time, itertools
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit
from typing import List, Dict, Any, Optional, Set, Tuple
from playwright.async_api import async_playwright
import subprocess
import shutil
import asyncio
import requests
from datetime import datetime

today = datetime.now().strftime("%Y%m%d")
month = datetime.now().strftime("%y%m")
month_dir = f"logs/i/{month}"
os.makedirs(month_dir, exist_ok=True)
filename = f"{month_dir}/scrap_ig_{today}.log"

# sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings

IMAGE_DIR2 = settings['IMAGE_DIR2']
BASE_SAVE_DIR = IMAGE_DIR2
# BASE_SAVE_DIR = r"D:\temp"

# ======== 설정 ========
USER_DATA_DIR = str(Path("./ig_profile-14").resolve())  # 세션 저장 (2회차부터 자동 로그인)  # fx014 // dlsdn317!
# USER_DATA_DIR = str(Path("./ig_profile-1").resolve())  # fx015
# USER_DATA_DIR = str(Path("./ig_profile-16").resolve())  # fx016.. 사용하지마_법무부_
HEADLESS = False

USERNAME = settings['SCRAP_USERNAME']   # 인스타 로그인 계정
# USERNAME = 'fkaus014'
PASSWORD = settings['SCRAP_PASSWORD']   # 비밀번호
# PASSWORD = 'dlsdn317!'

# USERNAME = ""   # 인스타 로그인 계정
# PASSWORD = ""   # 비밀번호

# 스크롤/속도
SCROLL_PAUSE = 1.8
MAX_SCROLLS = 30001
DELAY_SECOND = 2.0
DELAY_MINUTE = 60 * 5
ALREADY_COLLECTED_COUNT = 40

# ── CDN/응답 필터 설정: 리전/세그먼트 버전 다양성 대응 ─────────────────────────────────────────
CDN_HOST_RE   = re.compile(r"^https://scontent-[a-z0-9\-]+\.cdninstagram\.com/") # scontent-ssn1-1 등
CDN_PATH_ALLOW= re.compile(r"/o1/")   # # /o1/ 경로 포함 (t2, t16 등 세부 버전은 다양), 필요 시 |/o0/ 등 추가
MIN_GOOD_VIDEO_BYTES = 500_000        # 0.5MB 이상만 후보

# 동시 다운로드 제한
MAX_CONCURRENCY = 4
# 팔로우 btran24x
ACCOUNTS = [
    # 'im____neko', 'btran24x',
    # 'eul_jj', 'yeoxoho', '_loveys_', 'loaju____', '77sweetybee', 'happyunaaa', 'minginggg', 'angelinababyxx77',
    # '____yoming', 'sehee2_2', 'himira_baby', 'suyyyisss', 'hw._____2', 'chaeero', 'minjeong48576', 'bibi_0_0_11',
    # 'x_arielxx', 'daaasomm', 'queenzy_qzy', 'lingdfg', 'eundew_gondew', 'gemmanotalone_', 'dailyssong', 'ttokkenge',
    # 'nana.k9901', 'qaaallaq', 'daisy.baby1004', '8701jll', 'phoebe_.xn', 'lilygumii', 'within_elin', 'florso0',
    # 'ana_nyang', 'cutey.wolf', '7ouhwon', 'gu___gubear', 'linhlinhchip', 'salysaouk', 'ngquynhnhi_qni', 'Phanva_vye',
    # '1.21.apm', 'nahaneulll', 'xviimpr__', 'hiyroze', 'su____0717', 'da.seol_', 'uneed___y', 'jaamietan',
    # 'm._.eeo', 'jiyeonova', 'lxvefrxmnxc', '_uchu_uchu_123', 'hhr_301', 'zyzyveve', 'yonuonly', 'rika7me',
    # '11sukiyo', 'snusnu', 'neine.ipupu', 'zav_by1', 'seaofy._', 'smorebin', 'm1nzng', 'ztc_713', 'meinvjihe',
    # 'k_02kg', '_91yu', '___wuyou', 'callmemira926', 'mikanaka95', 'kmiseo___', 'jjimmy.am', 'kyliett1', '_scotthh_',







    # 다시 시작할때는 아래부터
    # 'ja_y_0_0', 'dumb_pink6', '456818_luv', '_joon__e', 's2.aaaaaa', 'eye.luv.uuu', 'songzi_won', 'kk.kyl0',
    # 'miemayon', 'nguyenry_na05', 'miisu000', 'xiiaom_life', 'kurosakiqiqi', 'irysl', 'kyu__ming', 'yuina6867',
    # 'luv_mr.9', 'e_unzni', 'so_rabimu', 'niya.gerda', '_j_sy', 'michi1.8', 'j_reve__', 'ria0kcal', 'asyalikizpaylasiom',
    # '_._.min.s_', 'jena.legs', 'yeosney', 'heduolexiangtu00', 'nanaboa_s2', 'itsjihoooo', 'xeoeunx', '_jiiyou',
    # 'lijiamin922', 'qiuuuqiu', 'j__oony', 'meowsso', 'babyjiin_', 'yxx.jj', 'suu.eun', 'soxuni_6', '_____serendip1ty__',
    # 'fall_s2_', 'hm2.j', 'eeu_nkyo', 'fei210k', '__soften__', 'tokki_0_0_', 'sseunaa', 'yeoonge',
    # 'jiminnx_', 'nyeoie', 'maruemon_96', 'newwwspring2', 'so1rblu', 'jju_dxeng', 'ximi_v', 'asianbunnyxu',
    # '_dahyexn', 'juicy_s2_', 'i.a.m.joy_', 'pm16._.00', 'imparkseoyi', 'voos._.soov', '6nthespot_j', 'passerby_383',
    # 'cheeerry_g', 'heesu._.ji', 'j1won.ver', '___ffany___', 'jelly._cc', 'h_aeining', 'kimkkukku_vv', '7ee7in',
    # 'karineeee_j', 'elina.xuanxuan', 'serenaa_xy', 'somi.yii', 'sowol.2', 'jellymon_', 'hyoca_v', 'breathsums',
    # 'nimkguyen', 'riya_yu', 'lovelynnboo', 'becky.o9o', 'celi.nejy', '_imnyx', 'seven.eso', 'sansanbaebae',
    # 'showa_shojo', 'sirobutadesu', 'yyuu_1127._.1', 'hazzumerirong', 'jeemneee', 'banita.jin', 'suzziiiiy',
    # 'composer_seol', 'h_______hrin', '0lin97', 'sh_4.2.0', '_____jen2', 'rangpila', 'meowhae_02', 'p0_0q_12',
    # 'mypinktension', '3.18_jy', 'sonnyxux', 'mer_maid_io', 'bada_00k', 'xyoungna', 'by_seoa', 'queenzy._nail',
    # 'bin___chuuu', 'jihyetty', 'ji.eunnii', 'juju__.s', 'itsmin_j', 'im_your_jyeon',
    # 'alicejungxx', 'hwangbabi.owner', 'soxxhui', 'sunn416', 'kasagi.cos', 'gar_dxx',
    # 'jangjang.97', 'syx_janeyoo', '_s_j_sonyeo', 'dyonni__', '_pmk___', 'ye._.rry', 'mikanaka9999',
    # 'godrhea', 'offmmin', 'bo_ming__', 'mia0.713', 's_b_131', '2u_fairy', 'rosie_weiwei',
    # 'kurosakiqiqi', 'ruri_azurrum', 'sakura_maomao', 'hopxheex', 'love_zennyrt', 'nyangcre', 'i.am.sehee',
    # 'yunyunyun01', 'duyenn.hipp10_4', 'duyenn.hipp10_4', 'junglnside', 'uxx.mee', 'mimi___2k', 'yoodaye__',
    # 'syb.3_3', 'gisele_48', 'p_a_s_s_o_u_t___', 'tmfrl5687', '__e_zz', 'ji_hye._.choi', 'xtrzssss',
    # 'chaeee222', 'llovelydday', 'ellie.yh.kim', 'eatha_02', 'niuu.yh', 'only_jin_want', 'ha_lklk',
    # 'jeonsebin606', 'starlike999', 'pdpd_xixe', 's2eeena1_214', 'g.xyn_8',
    # 'jinyomissong', '24.yu_', '1004yyyyyy', 'ini_113', 'cocoyoen', 'gahee_lov', 'xoxojiyu', 'y._.yun__',
    # 'linhtho_06', 'qtd___', 'onvi2ee', 'a_iridescence', 'spring_.0304',
    # 'taemmimm', '_uni_j', 'haenni_48', 'jji__chuuu', '__etre0301', 'serein_rin', 'eddddnnn', 'yeah_niii',
    # 'star.1ikeu', 's_ye__j', '09x05', 'dgeneva___', 'hiandme_lhj', 'hanlalahh', 'eliteiaai',
    # 'yena_.nya', '9530.2', 'glea.mingsoi', 'seoren__________', 'eyu.xx', 'yelinnne',
    # 'innooonni', 'sseuldl', '0224y_y', '__khina.z',
    # 'yua_voxy', 'takomayuyi', 'zuozuo0701', 'kekexiyyy_', 'iam_victoria_dream', 'mmikobbb', 'xiianger',
    # 'lovel__yuu', 'hsxxa_', 'sxxg_a', 'xixigina', '4saruru', 'jjuya_o0o', '_______sooah_', '__habin_s2',
    # 'noonnyvichudawan', 'hbbxx_milk', 'x2_w2_', 'xx1oo9', 'love.been_', 'jelly_riri_', 'evolyvul__',
    # 'vely.mom', 'xx_miiyo', 'g.lita._', 'viviana___jung', 'binnnibii', 'bjju.__.jj', 'bini._.9', '__mjie__',
    # 'yundeun_', 'nna_yomi', 'serena__sy', 'seoyoon282', 'haeun_______', 'xxyspx_xx',
    # 'vivivxxy__', 'gnaranha', 'a.ming_s', 'xx_sunh_xx', 'lee_so0810', 'lovres_min_',
    # 'bibee2ee', 'sun_ssilver', 'neutral_magazine_', 'cotton.un', 'hayounngg', 'adorable.ssin',
    # 'love._.lett', 'iamsxxy', 'jun.amaki', 'm3dusa_9', 'tawanptn', 'sine_swxgg', 'xxhannipxx',
    # 'byhyunbi', 'inah_sekiz05', 'tt_congg', '75.twl_', 'rmrm_1813', 'peach__army',
    # 'rosy_una_yyy', 'egg_egg0.0', '_dear_bella_', 'pilaxxs', 's_fute19', '16.7_kg',
    # '171___55', 'sia2_2a', 'sha2_s2022', 'minhanna0914', 'babyswims.sg', 'kabiqiu',
    # 'pat_parichat_', 'natty_n22', 'l70.4_', 'hyo.j.u', 'onlyone_zin', '_young2._', 'cocoxreal_', 'hzzu__u',
    # 'n0b0dye1se', 'zyeoooon', 'new.and.b', '7x3gram', 'serin.2am', 'huru.huruu', 'bababibear__',
    # 'sheknoh', '173_sj', 'ringo_lyn', 'via_olivia_xoxo', 'o9__o8', 'yn____say',
    # 'me.ow_me.ow_', '175_pyeon', 'l2.sh__', 'hip_pretty', '3.26._.c', 'you_mini_da',
    # 'hajiwon.22', 'bisoou_uu', 'bbgrbttr', 'yoon._.vely2', 'hahahazwoo', 'iii_17.0', 'sook_0', '_silver_snow_',
    # 'dahye_1lee3', 'jeehyeounn', 'chaae.rin', 'jini_bbangg_', 'kimgapju', '_aarome', 'soooobxxn', 'sexy_minji_',
    # 'yoomstagramm_', 'hbbxx_s2', 'l_mh92', 'starlight_h20', 'j_i_y__', 'pilason._',
    # 'jiseon_tv', 'jini__0227', 'slowswan', '___jung.g', 'haminiii', 'chaexnn', 'myu_a_',
    # 'won._.niii', 'hana_sooong', 'xo_yeri', 'floretta__', 'floretta_for_summer',
    # 'chaey17', 'neejinee', 'u.zyn', 'popoyehh', 'kalokagatxia', 'from__honeyvivi', 'jeee622',
    # 'berryooon', '11.3bin', '__jan.7', '0y_joo0', 'dig_gi', 'love.bitt', 'u__v.ely', 'emmmshin',
    # 'tian_meiso', 'swai_sy', 'shushu_2.1', 'n__yoonn', 'h_s.s2', 'yee.rimi',
    # 'si.young', 'vivixch', 'yea_rang', '6.15zm', 'xxaxix_', 'diamant.ete', 'aa_yoon',
    # 'coszmy', 'eu_nj', 'zhuhaina', 'an_xna_', '__dmswl_',
    # 'seultori_510', 'yuri_luffy', 'iamruzzxng', 'song__ji_', 'sukimi0320', '_xem__i',
    # 'svn9o.__.ww', 'da._.hae12', 'iloveyou._.3000', 'rinrin.zip', 'ceunee', 'guswl_0409', 'ttt.ri',
    # 'green.teabag', 'ji2une', 'ye.__119', 'ssoyeomi', 'nannychanada', 'faiisukanya.6992', 'candyseul',
    # 'bin___0812', 'oaoagirl', 'badass._.sky', 'jeje_482', '_oucci___',
    # 'ellaeaaa', 'chaeri__.s2_', 'lovley__zuzu', 'o_8.6', 'iilike.0',
    # 'honey___bikini', 'otracyo8', 'ahyo12_07', 'roxeuoon',
    # 'p___nr', 'jiee_wen', '_lovely.jin', 'miya.02822', 'ji__sunny_', 'lim__bell',
    # '_heeyomii', 'yund_s2', 'gaheunii', 'bai_zzi', 'flora_0ne', 'yyy_123n',
    # 'xrkghk_.h', 'jiminbaby_s2', 'si_.yoni', 'gyuky_', 'you.nique9', 'bo.nn._y', 'th_exy',
    # 'my._ju', 'seo__0.x', 'nowex._', 'hhauuni', 'crewme_academy', 'f0iury_1', 'vuv_lly',
    # 'luvbbeen', 'eve_noh_', 'sorakxx', 'cooomong', 'arreumii', 'suxgexn',
    # 'vivian____e', 'loveeee___168', 'ggyong_ee', 'sys2_s2', 'yourmuseisu',
    # 'yaozhuzhu_', 'suming_ee', 'nanaring_', 'm._ung', 'dear.araminta', 'kkang.nyang',
    # 'ddo._.uuuu', 'mintbaka', 'ssol_ra.c', 'blossom_rim___', 'yea__won_', '_i.magine_', 'sovely_fit',
    # 'baek_nahyun_', '_.0_.oo', 'valennjy', 'richyaaaaaa',
    # 'key_ssam_', 'fullmooon___', 'doa_1224', 'dh_oh_eb', '0_gwlny', 'uyuy_joo', 'jonye.com_',
    # 'seohavivi', 'rh_ab', 'boonong_lovely', '_peachme_', '875cos', 'xisiun', 'youvlyna',
    # 'hee._.tty',  'heeya_cosplay', 's2_u.l', 'ww0205ww', 'soo_flower',
    # 'daaddaad_daad', 'myelnday', 'zl_rlo.k', '_sorang__', 'signal_jung', 'jaewoneey', 'lamianxiong7717',
    # 'samura2.heart', '92ddo', '2.09ke', 'bhabiesol', 'heenyang___', 'bambiaura9999',
    # 'shavit_khan', 'uzoolike_', 'lilithzxm', 'dlove_x', '0_u_ng',
    # 'rogle__', 'aomsin.wrp', '36.mxmxyyy', '_hyounj', 'hyxmimi',
    # 'hee.zini', 'lluvly_', 'binxnnn', 'crystalgramx', 'sojjing', 'furee999', 'c.haee_', '5.24_c',
    # 'kinnjust', 'd_bani97', 'd___q_', 'k__xiin', 'ming_cute_', 'zisoooop',
    # 'aonaumaaa_', 'velyroom', 'hoi__yoon', 'hal.h.l', '___eunluv', 'grxra', 'juneeexoxo',
    # 'so.tamin', 'e_y00', 'eun2ang', 'yunseul_000', 'hxxmiso', 'dear._.jung',
    # 'kangtokki_', 'cheap_box', 'its_suzy_time', 'amourfor_u', 'o___jin.a_', 'wellhari_',
    # 'so0o_h_', 'sinyxii', 'ch__hana', 'so_love_so_', 'hoy_ni_', 'luvurse1f_',
    # 'pu.___', '7.10h', 'chennierubychane', 'inooyeah', 'imyeonduu', 'beloved__yoo',
    #
    # # cleanup --------------------------------
    # 'angel_youn', 'vvknkk', 'cherish.__h', 'akdeb_', 'iamyeoninn', 'mio_love_y', 'cha_sohyeon',
    # 'yisoah', 'pilarim__', 'signoey', 'nuuzln', 'yuanweiibing', '__jihyang_',
    # 'i_ye0ni_', 'loyewe_official', 'seo.ohh', 'dduen2', 'baby__rosy_',
    # 'h0_barbie', 'beena._s2', 'se0kxxg', 'min_vely__26', '_9.km', 'kss0x', 'ssoyababe', '_chae_rin2',
    # 'kyoungsxx', 'realminzu', 'davely__o', 'oasis_0_0', 'lovelykce', 'sin_e_g', 'soo_dayo2', '10o4z', 'a.__.rume',
    # 'selpo_s2', 'sonming52', 'i_am_young22', 'cosyounghere', 'momokini_com',
    # 'yasal_170', 's0zzzi', '_jinuary_', 'ye0n2yo',
    # 'c_dbfl', 'its_hr_time', 'red.bell3', '__szimpatikus', 'soapurin', 'joj._.uk',
    # 'ddohyun', 'j1ns1m', 'soo_m___', 'leedahve', 'sara.co.k', 'zennyrt', '____gyom',
    # 'siu.im', 'su0rla', 'yeji._.joo', 'wankeeratiya', 'u__stagram__',
    # 'ye.eun_son', '_hheya', 'eiiiiiiem', 'kingvivianelee', 'nar1n_2', '_sumang._', 'xov.xul_',
    # 'earnjubu', 'xouuuus', 'lssaaxx', 'closecurve_official', 'j.warm_', 'zero0silver',
    # 'g.naaaa_', 'soyeemilk', 'soyee.milk', 'le_wnyoung_', 'love__coc0', 'zizihyun080', 'zzuu.___', 'xeuul_',
    # 'minimini_1004', '_dudu_di_', 'sonyearin', 'b_____star', 'youdaeng__', 'egg00_2.0',
    # 'lovejaewonzz', 'h_a_c_a_', 'rlwndud05_', 'jihyun_09_16', 'yoo.oonni',
    # 'hypnotic.co.kr', '_kkhj2', 'prettygirl__stagram__',  'hyan_08', 'hyerininng', 'the._.2y',
    # 'ejyoooou', 'charming__ny', 'jdabyeol2', 'gu__zzzi', 'simgaram', 'inkyung97', 'xon_ah',
    # 'seoulasuna', 'harinxchu', 'dltnqls823', 'jia__a', 'so__w0n', 'sux_eon', 'xeva.qiaoniutt',
    # 'xxinchye_', 'h1_chu_', 'lilly_11029', 'seon_h_e', '59.5994', 'susan.n426', 'seo._.llll',
    # 'kim_s_ofo', 'svvvnswan', 'koreangirlsontop', 'obolzr_', 'uni_h_',
    # 'bi._.kini', '_wj._d', '9.74kg', 'subni0.0', 'lylakong01', 'xiaoyou_uzi',
    # '70g_ee_y', 'xmoonoa', 'bodyon_bikini', 'soouine', 'star____b._', 'yu._.mei', 'necomimi_b',
    # 's0on_ho', 'ju_.vely_', '_yj2.18k', 'youuuu_d', 'u__stagram__', 'y_chaeee', 'heex.x_', 'roongzie',
    # 'meww.jin', 'myuxxrv', 'y._.dulcet', 'p.___.gj', 'si_euns2', 'in2327_h', 'jihea_a', '5959__50',
    #
    # # 비공개였다가 공개된 계정들
    #  'xaevev', 'seasooseasoo', '171.mc', 'eunnhong', 'arinm_1204', 'dinnydyu', 'no.park.gu_', 'jiyouxn', 'sen.xy_',
    #
    # # 비공개 계정들
    # '728mz', 'cherrytohearts', 'viesuzami', 'eoxnyx', 'immzoo',
    # 'zzyuridarong', '_ha_nari_', 'nn_yun_s', '2pendency', 'koberryy',
    # 'anhamm_1111', 'ba.kkung', 'jxngxxin', 'zzyuridayo', 'leeae_ai', 'jjo_nyxx',
    #
    #
    # # 삭제프로필
    # 'baberamii', # (가룸)
    # 'chocomintteri', 'yasminabb_', 'xipduksoojeong', 'jqbabyby', 'onibaby2001', 's2ena2', 'h___rvn', 'sunny_chijnn',
    # 'jxngxxin', 'aoi._.9z', 'qiaoniu1987', 'sindabazzi', 'godseolhwa', 'yun_iia', 'ps.eunji', 'jnxul',
    # 'iam_besso', 'loveynynyn', 'jy_911', 'lasy_243', 'serimm11', 'wonyforone', 'ne_0_ie', 'se.rin.06',
    # 'necomimivv', 'hmmmem', 'llilyylux', 'nhagirlxinh', 'meimeii.99', 'miyukiicos', 'vunarz', 'yeonyuneko',
    # 'dirinzero', 'mandy__nana', '_qingzi00', 'jinheeru', 'j.nsul', 'hyexnst', 'songe_love07',
    # 'siyeon_lovee', 'ryu._sy', 'uhwa_171', 'nameisgrvn1015', 'banseozi', 'by_jin06', 'yuuko_uzi',  'jiwon.lee_06',
    # '0.0_ey', 'ulzzanggirlasia__', 'illl__._', 'tatayatatay', 'ssuduck', 'iamharuzzxng', 'catjjoa',
    # 'youcantbejennifer_', 'ivytt77', 'zoeeecsy_sy', '3.sun.2', 's_jisu_02', '9_9hop', '2week_ago', 'fuxi_korean',
    # 'fluffycandyrat_', 'himenoyudii', 'meiyouyuanzi_001', 'julia_yang01', 'eunj._.ya', 'areuumm__', 'the.muse_elen',
    # 'rim._.kim',
]
# ACCOUNTS = ["fkaus014"]  # 스크랩 대상 계정 배열


ERROR_LINKS = [

]






# ======== 유틸 ========
def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name)

def ensure_dirs(base: str, account: str) -> Dict[str, str]:
    base_acc = os.path.join(base, account)
    img_dir = os.path.join(base_acc, "images")
    reel_dir = os.path.join(base_acc, "reels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(reel_dir, exist_ok=True)
    return {"base": base_acc, "images": img_dir, "reels": reel_dir}

def guess_ext_from_url_or_type(url: str, content_type: Optional[str]) -> str:
    if content_type:
        if "image/" in content_type:
            return ".jpg" if "jpeg" in content_type else f".{content_type.split('/')[1].split(';')[0]}"
        if "video/" in content_type:
            return ".mp4"
    # fallback to URL path
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    if ext:
        return ext.split("?")[0]
    # ultimate fallback
    if "/video" in url:
        return ".mp4"
    return ".jpg"

def is_post_or_reel(url: str) -> bool:
    try:
        path = url.split("?")[0]
        return "/p/" in path or "/reel/" in path
    except Exception:
        return False

def is_media_response(resp) -> bool:
    try:
        ct = (resp.headers or {}).get("content-type", "")
        return ("image" in ct or "video" in ct) and not resp.url.startswith("blob:")
    except Exception:
        return False

# --- helper: ffprobe로 비디오 길이(초) 가져오기 ---
def get_video_duration_sec(path: str):
    """
    ffprobe(FFmpeg) 필요. 성공 시 길이(초) float, 실패 시 None 반환.
    """
    if shutil.which("ffprobe") is None:
        # ffprobe 미설치
        return None
    try:
        # duration만 깔끔하게 출력
        # 참고: 일부 파일은 format.duration 대신 stream.duration이 필요할 수 있어 단순 출력 사용
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path
            ],
            capture_output=True, text=True, timeout=10
        )
        out = (res.stdout or "").strip()
        if not out:
            return None
        return float(out)
    except Exception:
        return None

def canonical_cdn_key(u: str) -> str:
    """
    쿼리스트링은 무시하고, host+path만 키로 사용 (동일 리소스 중복 제거).
    예: https://scontent-.../o1/v/t2/abc.mp4?efg=... -> scontent-.../o1/v/t2/abc.mp4
    """
    p = urlsplit(u)
    return f"{p.netloc}{p.path}"

def extract_account_and_type(url):
    # URL 파싱
    parsed = urlparse(url)
    # print(parsed)
    # ParseResult(scheme='https', netloc='www.instagram.com', path='/fkaus014/p/DO27U_DDw63/')

    # 1) 기본 도메인 (https://www.instagram.com)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # 2) path 부분 나누기
    parts = [p for p in parsed.path.split("/") if p]  # 빈 문자열 제거
    # parts = ['fkaus014', 'p', 'DO27U_DDw63']

    # username = parts[0]  # fkaus014
    # post_type = parts[1] # p
    # post_id   = parts[2] # DO27U_DDw63

    post_type = parts[0] # p
    post_id   = parts[1] # DO27U_DDw63

    return {
        "type": post_type
    }

# ======== 브라우저 조작 ========
async def ensure_login(page):
    await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    await asyncio.sleep(4)
    # 로그인 폼 보이면 로그인
    login_user = page.locator("input[name='username'], input[name='email']")
    login_pass = page.locator("input[name='password'], input[name='pass']")
    if await login_user.count() and await login_pass.count():
        await login_user.fill(USERNAME)
        await login_pass.fill(PASSWORD)
        await login_pass.press("Enter")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(10)
        # 팝업 닫기
        for txt in ["나중에 하기", "Not Now"]:
            btn = page.locator(f"button:has-text('{txt}')")
            if await btn.count():
                await btn.click()
                await asyncio.sleep(1)

async def go_to_profile(page, handle: str):
    url = f"https://www.instagram.com/{handle.strip('/')}/"
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_selector("main", timeout=30000)


POST_PREFIXES = {"p", "reel", "tv", "stories"}  # IGTV 포함(필요 없으면 제거)

def normalize_ig_post_url(url: str) -> str:
    """
    https://www.instagram.com/<user>/p/<code>  -> https://www.instagram.com/p/<code>
    https://www.instagram.com/<user>/reel/<code> -> https://www.instagram.com/reel/<code>
    이미 /p/, /reel/, /tv/ 로 시작하면 그대로 유지.
    쿼리/프래그먼트 보존, 상대경로도 허용.
    """
    base = "https://www.instagram.com"
    s = urlsplit(urljoin(base, url))  # 상대경로 대비
    parts = [seg for seg in s.path.split("/") if seg]  # ["user","p","CODE"]

    if len(parts) >= 2 and parts[0] not in POST_PREFIXES and parts[1] in POST_PREFIXES:
        # 첫 세그먼트가 유저명이고, 그 다음이 p/reel/tv 인 전형적 패턴 → 유저명 제거
        parts = parts[1:]

    new_path = "/" + "/".join(parts) if parts else "/"
    return urlunsplit((s.scheme, s.netloc, new_path, s.query, s.fragment))


async def collect_post_links(page, max_scrolls=MAX_SCROLLS, pause=SCROLL_PAUSE) -> List[str]:
    """프로필 페이지에서 스크롤하며 /p/, /reel/ 링크 수집 (상대경로 → 절대경로)"""
    links = []
    post_links: Set[str] = set()
    # stable_rounds = 0
    # last_count = 0
    already_collected_count = 0
    await page.wait_for_selector("main", timeout=20000)
    # await asyncio.sleep(5)

    # 처음에만 게시물 링크가 뜰 때까지 최대 10초 기다림
    try:
        await page.wait_for_selector('a[href*="/p/"], a[href*="/reel/"]', timeout=10_000)
    except:
        pass

    last_height = await page.evaluate("document.body.scrollHeight")

    for _ in range(max_scrolls):
        anchors = await page.locator('a[href*="/p/"], a[href*="/reel/"]').element_handles()
        if len(anchors) == 0:
            print('[ERROR-1] ★★★★★★★★★★★★★★★★★★★★★★★ Account is not valid ★★★★★★★★★★★★★★★★★★★★★★★ ')
        for a in anchors:
            href = await a.get_attribute("href")
            if not href:
                continue

            # 절대경로화
            if href.startswith("/"):
                # href: /계정/p/postId/
                parseResult = urlparse(normalize_ig_post_url(href))
                origin_href = parseResult.path

                href = urljoin("https://www.instagram.com", href)

            # acount 세그먼트 제거
            # href = normalize_ig_post_url(href)

            if is_post_or_reel(href):
                if already_collected_count > ALREADY_COLLECTED_COUNT:
                    rev_links = links[::-1]   # slicing, 원본 보존
                    return rev_links

                url = "https://chickchick.kr/func/scrap-posts?urls="+origin_href
                res = requests.get(url)
                try:
                    data = res.json()
                except ValueError:  # JSONDecodeError도 ValueError 하위
                    print("[WARN] https://chickchick.kr 서버 응답없음")
                    return []
                if data["result"]: # 등록되어 있음
                    already_collected_count += 1
                    continue

                if href not in post_links:
                    post_links.add(href)
                    links.append(href)

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await asyncio.sleep(pause)

        # 새로운 콘텐츠 로딩됐는지 확인
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            # 더 이상 늘어나지 않으면 종료
            break
        last_height = new_height

        # await page.evaluate("window.scrollBy(0, Math.max(400, window.innerHeight*0.9));")
        # try:
        #     await page.wait_for_load_state("networkidle", timeout=3000) # 스크롤 후 대기(최대)
        # except:
        #     pass
        # await asyncio.sleep(pause)
        #
        # if len(post_links) == last_count:
        #     stable_rounds += 1
        #     if stable_rounds >= 3:
        #         break
        # else:
        #     stable_rounds = 0
        #     last_count = len(post_links)

    # return sorted(post_links)
    # links.reverse() # 역순으로 뒤집기
    # return links

    rev_links = links[::-1]   # slicing, 원본 보존
    return rev_links

# 컨테이너: section > main > div:first-child > div:first-child > div[role="presentation"] > ul > li > img
"""
UL_SEL   = "section main > div:nth-of-type(1) > div:nth-of-type(1) div[role='presentation'] ul"
LI_SEL   = UL_SEL + " > li"
IMG_SEL  = UL_SEL + " > li img"
FALLBACK_IMG  = "section main > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) img"
NEXT_BTN_SEL  = (
    "section main > div:nth-of-type(1) > div:nth-of-type(1) "
    "button[aria-label*='다음'], :has(button:has-text('다음')), "
    "button[aria-label*='Next'], :has(button:has-text('Next'))"
)
"""

# 공통 루트
ROOT_MAIN   = "section main > div:nth-of-type(1) > div:nth-of-type(1)"
ROOT_DIALOG = "div[role='dialog']"

async def _resolve_root(page) -> Tuple[Optional[str], Optional[str]]:
    """메인 루트 우선, 없으면 다이얼로그 루트 선택. (root_css, kind) 반환"""
    try:
        await page.wait_for_selector(ROOT_MAIN, timeout=2500)
        if await page.locator(ROOT_MAIN).count():
            return ROOT_MAIN, "main"
    except Exception:
        pass
    try:
        await page.wait_for_selector(ROOT_DIALOG, timeout=4000)
        if await page.locator(ROOT_DIALOG).count():
            return ROOT_DIALOG, "dialog"
    except Exception:
        pass
    return None, None

def _under(root: str, rel: str) -> str:
    """루트 아래 상대 셀렉터를 절대 셀렉터로"""
    if not rel:
        return root
    return f"{root} {rel}".strip()

def _sel(root: str, kind: str, rel_main: str, rel_dialog: Optional[str] = None) -> str:
    """루트 종류에 따라 알맞은 상대 셀렉터를 선택"""
    rel = rel_main if kind == "main" else (rel_dialog if rel_dialog is not None else rel_main)
    return _under(root, rel)

async def extract_imgs_src_only(page, post_url: str, seen: Set[str]) -> Tuple[List[str], List[str]]:
    root, kind = await _resolve_root(page)

    # 루트/종류에 맞춰 모든 셀렉터 구성
    if root:
        # 캐러셀 UL/LI/IMG
        UL_SEL  = _sel(root, kind, "div[role='presentation'] ul")
        IMG_SEL = _sel(root, kind, "div[role='presentation'] ul > li img")

        # 다음 버튼 (버튼 "자체"만 선택)
        NEXT_BTN_SEL = ", ".join([
            _sel(root, kind, "button[aria-label*='다음']"),
            _sel(root, kind, "button:has-text('다음')"),
            _sel(root, kind, "button[aria-label*='Next']"),
            _sel(root, kind, "button:has-text('Next')"),
        ])

        # fallback IMG (루트 기준)
        FALLBACK_IMG = _sel(root, kind,
                            rel_main="> div:nth-of-type(1) > div:nth-of-type(1) img",
                            rel_dialog="img")
    else:
        UL_SEL = IMG_SEL = NEXT_BTN_SEL = None
        # 루트를 못 찾으면 둘 다 커버
        FALLBACK_IMG = (
            "section main > div:nth-of-type(1) > div:nth-of-type(1) "
            "> div:nth-of-type(1) > div:nth-of-type(1) img, "
            "div[role='dialog'] img"
        )

    # 1) UL 대기 (있으면 캐러셀 모드, 없으면 fallback)
    ul_found = False
    if UL_SEL:
        try:
            await page.wait_for_selector(UL_SEL, timeout=5000)
            ul_found = True
        except Exception:
            ul_found = False

    # 공통: 이미지 한 번에 최대 해상도만 수집
    async def collect_max_images(selector: str) -> List[str]:
        try:
            n = await page.locator(selector).count()
            if n > 0:
                await page.locator(selector).nth(n - 1).scroll_into_view_if_needed()
        except Exception:
            pass

        urls: List[str] = await page.evaluate(
            """
            (sel) => {
              const pickLargestFromSrcset = (img) => {
                const ss = img.getAttribute('srcset');
                if (!ss) return null;
                const items = ss.split(',').map(s => s.trim()).map(entry => {
                  const [u, d] = entry.split(/\\s+/);
                  let w = 0;
                  if (d && d.endsWith('w')) {
                    const n = parseInt(d.slice(0, -1), 10);
                    if (!isNaN(n)) w = n;
                  }
                  return { url: u, w };
                }).filter(it => it.url);
                if (!items.length) return null;
                items.sort((a,b)=>b.w-a.w);
                return items[0].url;
              };

              const preferAttrs = (img) => {
                const cand = [
                  'data-src-large','data-src-2x','data-large','data-original',
                  'data-srcset','data-fullsrc','data-full','data-url'
                ];
                for (const a of cand) {
                  const v = img.getAttribute(a);
                  if (v) return v;
                }
                return null;
              };

              const imgs = Array.from(document.querySelectorAll(sel));
              return imgs.map(img =>
                pickLargestFromSrcset(img) ||
                preferAttrs(img) ||
                img.currentSrc ||
                img.getAttribute('src')
              ).filter(Boolean);
            }
            """,
            selector
        )
        return urls

    async def collect_video_srcs(selector: str) -> List[str]:
        urls = await page.evaluate(
            """
            (sel) => {
              const vids = Array.from(document.querySelectorAll(sel));
              const out = [];
    
              for (const v of vids) {
                let src = v.getAttribute('src') || v.currentSrc;
                if (!src) {
                  const source = v.querySelector('source');
                  if (source) {
                    src = source.getAttribute('src');
                  }
                }
                if (src) out.push(src);
              }
    
              return out;
            }
            """,
            selector
        )
        return urls

    good_video_urls: Set[str] = set()

    # 네트워크 응답에서 '좋은' 비디오만 즉시 선별 저장 (페이지에서 발생하는 모든 네트워크 응답(response)을 “이벤트로” 받아서 검사하는 패턴)
    def on_response(resp):
        if looks_like_good_video(resp):
            good_video_urls.add(resp.url)

    # 2) 캐러셀
    if ul_found and IMG_SEL and NEXT_BTN_SEL:
        VIDEO_SEL = _sel(root, kind, "div[role='presentation'] ul > li video")
        async def collect_from_main() -> None:
            for u in await collect_max_images(IMG_SEL):
                if u:
                    seen.add(u)

            for v in await collect_video_srcs(VIDEO_SEL):
                if v:
                    good_video_urls.add(v)

        await collect_from_main()
        page.on("response", on_response)


        # "다음" 클릭 반복 (클릭 전 수집 → 클릭 → 잠깐 대기)
        for _ in range(20):
            next_btn = page.locator(NEXT_BTN_SEL).first
            if not await next_btn.count():
                break

            # 클릭 전 수집(현재 화면)
            await collect_from_main()
            page.on("response", on_response)

            # 클릭
            try:
                await next_btn.click(timeout=1000)
            except Exception:
                try:
                    await next_btn.click(timeout=1000, force=True)
                except Exception:
                    break

            # await asyncio.sleep(0.5) # 시간 조정
            await asyncio.sleep(0.7) # 시간 조정

        # 마지막 한 번 더
        await collect_from_main()
        page.on("response", on_response)

    # 3) Fallback
    if await page.locator(FALLBACK_IMG).count():
        for u in await collect_max_images(FALLBACK_IMG):
            if u:
                seen.add(u)

    # ===== 4) (선택) 추가 중복 축소: 사이즈 파라미터 무시 키로 병합 =====
    # 같은 사진인데 ?w=, ?h=, =s2048 등만 다른 경우를 더 줄이고 싶다면 사용
    import re
    def norm(u: str) -> str:
        # 아주 보수적으로 몇 가지 사이즈 토큰만 제거
        #  - Google 계열: "=s1234" 꼬리 토큰
        u2 = re.sub(r'(=s\d+)(?=$)', '', u)
        #  - 흔한 width/height 쿼리파라미터 제거 (다른 토큰 보존)
        u2 = re.sub(r'([?&])(w|width|h|height|size|s)=\d+(?=(&|$))', r'\1', u2, flags=re.I)
        u2 = re.sub(r'[?&]+$', '', u2)
        return u2

    best_by_key = {}
    for u in seen:
        key = norm(u)
        # 같은 키면 더 긴(대체로 고해상도) URL을 보존하는 간단 규칙
        if key not in best_by_key or len(u) > len(best_by_key[key]):
            best_by_key[key] = u

    final_urls = list(best_by_key.values())

    # 로그
    # print(f"\n=== {post_url} ===")
    # for i, u in enumerate(final_urls, 1):
    #     print(f"[IMG {i}] {u}")

    return final_urls, list(good_video_urls)


def looks_like_good_video(resp):
    """좋은(완전) mp4 응답만 통과: 200 OK, video/*, CDN host, /o1/, 충분한 content-length, content-range 없음"""
    try:
        if resp.status != 200:
            return False
        # content-type
        ct = (resp.headers or {}).get("content-type", "")
        if "video" not in ct:
            return False
        # 조각 스트리밍 제외
        hdrs = {k.lower(): v for k, v in (resp.headers or {}).items()}
        if "content-range" in hdrs:
            return False
        # CDN host + 경로 규칙
        if not (CDN_HOST_RE.match(resp.url) and CDN_PATH_ALLOW.search(resp.url)):
            return False
        # 크기(있으면 체크)
        clen = hdrs.get("content-length")
        if clen and clen.isdigit() and int(clen) < MIN_GOOD_VIDEO_BYTES:
            return False
        return True
    except Exception:
        return False

async def force_play_video_if_possible(page):
    """비디오 보이게 하고 재생 유도 → 네트워크 트리거"""
    vid = page.locator("section main > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) video").first
    if await vid.count():
        try:
            await vid.scroll_into_view_if_needed()
        except:
            pass
    # 재생 버튼 클릭 시도
    try:
        play_btn = page.locator("button[aria-label*='Play'], button:has-text('Play')")
        if await play_btn.count():
            await play_btn.click()
            await asyncio.sleep(1)
    except:
        pass
    # JS로 강제 재생
    try:
        await page.evaluate("""
            (sel)=>{ const v=document.querySelector(sel);
                     if(v){ v.muted=true; v.play().catch(()=>{}); } }
        """, "article video")
    except:
        pass

# https://scontent-ssn1-1.cdninstagram.com/v/t51
async def extract_media_from_post(page, url: str):
    """
    어떤 URL이든(포스트/릴스) 이미지와 비디오를 동시에 수집.
    - images: DOM의 <img>에서 수집(+캐러셀 next)
    - video_cdn: 네트워크 응답에서 '좋은 mp4'만 즉시 선별(필요 시 DOM의 <video src>도 보조)
    """
    good_video_urls: Set[str] = set()

    # 네트워크 응답에서 '좋은' 비디오만 즉시 선별 저장 (페이지에서 발생하는 모든 네트워크 응답(response)을 “이벤트로” 받아서 검사하는 패턴)
    def on_response(resp):
        if looks_like_good_video(resp):
            good_video_urls.add(resp.url)
    page.on("response", on_response)

    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(DELAY_SECOND) # 시간 조정

    # 이미지 수집 (도우미 사용)
    seen = set()
    images, videos = await extract_imgs_src_only(page, url, seen)

    for v in videos:
        good_video_urls.add(v)

    # 비디오 수집: 보이게/재생 유도 → '좋은' 응답 대기
    await force_play_video_if_possible(page)

    # 잠시 재시도하며 응답 모으기(총 ~6초)
    for _ in range(4):
        if good_video_urls:
            break
        await asyncio.sleep(0.75) # 시간 조정

    # 보조: DOM의 <video src>도 수집(있을 수 있음) → CDN 필터 적용
    vids = page.locator("section main > div:nth-of-type(1) video")

    try:
        await vids.first.wait_for(state="attached", timeout=60000)
        n_vid = await vids.count()
    except Exception:
        n_vid = 0

    dom_video_srcs = []
    for i in range(n_vid):
        try:
            v = vids.nth(i)
            # 2) video src가 안 박히는 경우가 많아서 두 군데를 봄
            vsrc = await v.get_attribute("src")
            if not vsrc or vsrc.startswith("blob:"):
                # <video><source src="..."></source></video> 케이스
                src_el = v.locator("source").first
                if await src_el.count():
                    vsrc = await src_el.get_attribute("src")

            if vsrc and vsrc.startswith("http"):
                dom_video_srcs.append(vsrc)
        except Exception as e:
            print(f"[ERROR-3-0] video src 추출 실패 index={i}: {e}")
            ERROR_LINKS.append(url)
            pass

    # DOM/네트워크 합치고, 최종적으로 CDN 규칙으로 필터
    candidates = set(dom_video_srcs) | good_video_urls
    # video_cdn = sorted(u for u in candidates if CDN_HOST_RE.match(u) and CDN_PATH_ALLOW.search(u))
    unique = {}
    for u in candidates:
        if CDN_HOST_RE.match(u) and CDN_PATH_ALLOW.search(u):
            k = canonical_cdn_key(u)
            # 먼저 본(가장 '좋아 보이는') 원본 URL을 보존
            unique.setdefault(k, u)
    video_cdn = sorted(unique.values())

    return {
        "post_url": url,
        "images": images,        # 항상 채움(있으면)
        "videos": [],            # 사용하지 않으므로 빈 리스트 유지
        "video_cdn": video_cdn,  # 항상 채움(있으면)
    }


_seq = itertools.count()
_seq_lock = asyncio.Lock()

def now_ms() -> int:
    return int(time.time() * 1000)  # 사람 읽기 쉬운 벽시계 ms

async def next_seq() -> int:
    # 동일 ms 충돌 및 코루틴 동시성 대비
    async with _seq_lock:
        return next(_seq)

def safe_open_exclusive(path: str):
    # 존재 충돌 시 에러로 실패시키는 전용 오픈 (덮어쓰기 방지)
    return open(path, "xb")

# ======== 다운로드 ========
async def download_one(session: aiohttp.ClientSession, url: str, save_dir: str, prefix: str="media") -> Optional[str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                return None
            ct = resp.headers.get("Content-Type", "")
            ext = guess_ext_from_url_or_type(url, ct)

            ts = now_ms()
            seq = await next_seq()  # 타이브레이커
            fname = sanitize_filename(f"{prefix}_{ts:013d}_{seq:06d}{ext}")
            # fname = sanitize_filename(f"{prefix}_{int(time.time()*1000)}{ext}")
            path = os.path.join(save_dir, fname)
            data = await resp.read()
            with safe_open_exclusive(path) as f:
                f.write(data)
            # with open(path, "wb") as f:
            #     f.write(data)
            return path
    except FileExistsError:
        # 극히 드문 경합 대비 (다시 한 번 시퀀스 증가)
        seq = await next_seq()
        ts = now_ms()
        alt = os.path.join(save_dir, sanitize_filename(f"{prefix}_{ts:013d}_{seq:06d}{ext}"))
        with open(alt, "wb") as f:
            f.write(data)
        return alt
    except Exception:
        return None


async def download_media(images: List[str], videos: List[str], video_cdn: List[str], dirs: Dict[str, str], account: str):
    # 비디오는 video_cdn만 사용 (요구사항)
    video_sources = video_cdn if video_cdn else []

    # 중복 제거
    images = list(dict.fromkeys(images))
    video_sources = list(dict.fromkeys(video_sources))

    conn = aiohttp.TCPConnector(limit_per_host=MAX_CONCURRENCY, ssl=False)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = []
        for i, url in enumerate(images, 1):
            tasks.append(download_one(session, url, dirs["images"], prefix=f"{account}_img"))
        for i, url in enumerate(video_sources, 1):
            tasks.append(download_one(session, url, dirs["reels"], prefix=f"{account}_reel"))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok_paths = [p for p in results if isinstance(p, str) and p]

        # 🔥 비디오 길이가 1초 미만이거나(0 포함) 길이 판독 실패(None)면 삭제
        deleted = []
        for p in ok_paths:
            try:
                if os.path.exists(p) and p.startswith(dirs["reels"]):
                    dur = get_video_duration_sec(p)  # None이면 판독 실패
                    # 규칙: dur is None(길이 불명) 또는 dur < 1.0 → 삭제
                    if dur is None or dur < 1.0:
                        os.remove(p)
                        deleted.append(p)
            except Exception as e:
                print(f"[WARN] 파일 삭제 실패: {p}, {e}")

        if deleted:
            print(f"[INFO] {len(deleted)}개의 짧은/길이불명 비디오 삭제됨 (<1s or unknown)")

        # 삭제되지 않은 경로만 반환
        return [p for p in ok_paths if p not in deleted]


# ======== 메인 플로우 ========
async def handle_account(page, account: str):
    await ensure_login(page)
    await go_to_profile(page, account)

    if account == 'test':
        # 디버깅
        links = ERROR_LINKS
    else:
        # 링크 수집
        links = await collect_post_links(page)


    if len(links) > 5:
        today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
        print(f"[INFO] [{today}] [{account}] Collect Postlinks: {len(links)}")
    if len(links) > 300:
        await asyncio.sleep(60 * 30)  # 과도한 요청 방지

    # 저장 디렉토리 준비
    if len(links) > 0:
        dirs = ensure_dirs(BASE_SAVE_DIR, account)

    all_saved = []
    check_saved = []
    cnt = 0
    for idx, link in enumerate(links, 1):
        today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
        print(f"[INFO] [{today}] [{account}] ({idx}/{len(links)}) {link}")

        # parsed = urlparse(link)
        # # ParseResult(scheme='https', netloc='www.instagram.com', path='/fkaus014/p/DO27U_DDw63/')
        # qs_link = normalize_ig_post_url(parsed.path)
        # parsed = urlparse(qs_link)
        # print(f"[{account}] ({idx}/{len(links)}) {parsed.path}")

        cnt += 1
        # None, False, 0, '', [], {}, 모두 여기로 들어옴
        # if idx == 5: # 디버깅 테스트용
        #     break
        media = {
            "post_url": link,
            "images": [],
            "videos": [],
            "video_cdn": [],
        }
        for attempt in range(3):
            try:
                media = await extract_media_from_post(page, link)
                break
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    print(f"[ERROR-2] media 추출 실패-{attempt + 1}: {e}")
                    ERROR_LINKS.append(url)

            # print('media', media)
            # 이미지: 그대로 / 비디오: VIDEO_PREFIX만

        saved = None
        try:
            saved = await download_media(
                media.get("images", []), media.get("videos", []), media["video_cdn"], dirs, account
            )
        except Exception as e:
            print(f"[ERROR-3] 다운로드 실패 {e}")
            ERROR_LINKS.append(url)

        # print('saved', saved)
        all_saved.extend(saved or [])
        check_saved.extend(saved or [])
        if idx % 10 == 0 or idx+1 == len(links):
            today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
            print(f"[INFO] [{today}] [{account}] Interim check of number of saved files : {len(check_saved)}")
            check_saved = []
        link_segment = extract_account_and_type(normalize_ig_post_url(link))

        payload = {
            "account": str(account),
            "post_urls": link,
            "type": link_segment["type"],
        }
        url = 'https://chickchick.kr/func/scrap-posts'

        for attempt in range(2):  # 총 2번 시도
            try:
                requests.post(
                    url,
                    json=payload,
                    timeout=(3, 20)
                )
                break
            except Exception as e:
                print(f"[WARN] progress-update 요청 실패-{attempt + 1}: {e}")
                if attempt < 1:  # 첫 실패면 10초 대기 후 재시도
                    time.sleep(10)
                else:  # 두 번째도 실패하면 그냥 무시
                    pass

        await asyncio.sleep(DELAY_SECOND)  # 과도한 요청 방지
        if cnt % 300 == 0:
            await asyncio.sleep(60 * 30)  # 과도한 요청 방지
        elif cnt % 100 == 0:
            await asyncio.sleep(DELAY_MINUTE)  # 과도한 요청 방지


    await page.close()

    if len(links) > 0:
        print(f"[INFO] [{account}] Number of files saved: {len(all_saved)}")

    return len(links)

async def run_scrap():
    account_length = len(ACCOUNTS)
    if account_length > 0:
        log_file = open(filename, "a", encoding="utf-8")   # w: 덮어쓰기, a: 이어쓰기
        sys.stdout = log_file
        sys.stderr = log_file
        # print("이건 파일로 감")
        # raise Exception("에러도 파일로 감")

        sys.stdout.reconfigure(line_buffering=True)
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            # headless=HEADLESS,  # 주석하면 브라우저 off
            # viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )


        for i, acc in enumerate(ACCOUNTS):
            today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
            print(f"\n[INFO] [{today}] Start account processing: {acc} ({i+1}/{len(ACCOUNTS)})")

            try:
                page = await context.new_page()
            except Exception:
                context = await pw.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                page = await context.new_page()

            try:
                rs = await handle_account(page, acc)
            except Exception as e:
                print(f"[ERROR-4] [{acc}] Error in processing: {e}")
                continue

            if i < len(ACCOUNTS) - 1:
                if rs > 30:
                    await asyncio.sleep(DELAY_MINUTE) # 계정 간 쿨다운(선택): 과도한 접근 방지
                else:
                    await asyncio.sleep(30)

        if len(ERROR_LINKS) > 0:
            page = await context.new_page()
            await handle_account(page, 'test')

        await context.close()

    if account_length > 0:
        log_file.close()

def run_scrap_ig_job():
    # 이벤트 루프는 “스레드당 1개”가 원칙
    asyncio.run(run_scrap())

if __name__ == "__main__":
    '''
    asyncio.run(run_scrap)      # ❌ 함수 자체를 넘김
    asyncio.run(run_scrap())    # ✅ 코루틴 객체를 넘김
    '''
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_scrap())
    finally:
        loop.close()
        os._exit(0)  # anyio atexit 스레드 풀 경고 방지
