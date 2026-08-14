import os
import shutil

DEL_CNT = 1

def count_files_by_empty_dirs(a_dir, b_dir, c_dir):
    empty_dirs = []
    pass_dirs = [
        'f0iury_1', '0.0_ey', 'youvlyna',  '_dudu_di_', 'siu.im', 'ssoyeomi', '175_pyeon', 'myuxxrv', 'pat_parichat_',
        'kss0x', 'zero0silver', 'sys2_s2', 'baek_nahyun_', 'prettygirl__stagram__', 'ssoyababe', 'beena._s2',
        'l2.sh__', 'se0kxxg', 'akdeb_', 'vuv_lly', 'bambi_jesuis2', 'huru.huruu', '0_u_ng', 'berryooon',
        'eliteiaai', 'xxaxix_', 'zuozuo0701', 'rinrin.zip', '5959__50', 'yund_s2', 'y._.yun__', 'aoi_9z',
        'sha2_s2022', 'so__w0n', '_young2', 'sux_eon', 'in2327_h', 'cooomong', 'uni_h_', '4saruru', 'rika7me',
        'yisoah', 'love__coc0', '__szimpatikus', 's_jisu_02', 'soxxhui', 'onlyone_zin', 'hee._.tty', 'phoebe_.xn',
        'kalokagatxia', 'serin.2am', 'xov.xul_', 'callmemira926', 'lxzlqzp', '_young2._',
        'd___q_', 'ini_113', 'signoey', 'hyxmimi', '5.24_c', 'p0_0q_12', 'yoo.oonni', 'zennyrt', 'passerby_383',
        'seasooseasoo', 'charming__ny', 'binnnibii', 'himeno_yudi', 'onewinter.k'
        'juicy_s2_', 'da._.hae12', 'x2_w2_', 'floretta_for_summer', 'green.teabag', 'ddohyun', 'eunnhong',
        '70g_ee_y', 'yuanweiibing', 'rosie_weiwei', 'iloveyou._.3000', '173_sj', 'syb.3_3', 'momokini_com',
        'ji2une', 'sxxg_a', 'xx_sunh_xx', 'xx_miiyo', 'wellhari_', '7x3gram', 'zisoooop', 'fei210k', 'seohavivi',
        'yyuu_1127._.1', 'soo_dayo2', 'sen.xy_', 'cheeerry_g', 'jiyouxn', 'tokki_0_0_', 'hhr_301', '1.21.apm',
        'binxnnn', 'vivivxxy__', 'yasal_170', 'bo.nn._y', '1004yyyyyy', 'bibee2ee', 'cotton.un',
        'ye0n2yo', 'me.ow_me.ow_', 'soo_m___', 'xtrzssss', 'yee.rimi', 'haeun_______',
        'serena__sy', 'sirobutadesu', 'sia2_2a', 'sakura_maomao', 'dlove_x', 'hiandme_lhj', 'closecurve_official',
        'u.zyn', 'hhauuni', 'eiiiiiiem', 'only_jin_want', 'jihyun_09_16', 'ellaeaaa',
        '92ddo', 'hee.zini', 'lssaaxx', 'sinyxii', 'iamruzzxng', 'kabiqiu', 'n__yoonn', 'hbbxx_milk',
        'miya.02822', 'soooobxxn', 'love._.lett', 'innooonni', 'you_mini_da', 'within_elin', 'ryeo_11_',
        'youdaeng__', 'suu.eun', '_uchu_uchu_123', 'necomimi_b', 'da.seol_', 'kyu__ming', 'jinyomissong',
        '36.mxmxyyy', 'ye.eun_son', 'richyaaaaaa', 'selpo_s2', 'min_vely__26', 'aa_yoon', 'taemmimm', '_jinuary_',
        'iamyeoninn', 'gaheunii', 'nna_yomi', 'hyerininng', '_sorang__', 'chennierubychane', 'inkyung97',
        'uhwa_171', 'sexy_minji_', 'dinnydyu', 's_ye__j', '11sukiyo', '171___55', 'rogle__', 's0on_ho', '__e_zz',
        'yourmuseisu', 'eatha_02', 'jihea_a', 'inooyeah', 'yea__won_', 'minimini_1004', 'jiseon_tv', 'eye.luv.uuu',
        'crewme_academy', 'dduen2', 'l70.4_', 'bi._.kini', 'sorakxx', 'bin___chuuu', 'god.seolhwa', 'roongzie',
        'blossom_rim___', 'pilaxxs', 'mmikobbb', 'u__stagram__', 'im_your_jyeon', 'arreumii', 'its_hr_time',
        'voos._.soov', 'red.bell3', 'soxuni_6', 'pilarim__', 'bambiaura9999', 'b_____star', '_.0_.oo', 'hoy_ni_',
        'yea_rang', 'nuuzln', 'meww.jin', 'zhuhaina', '___eunluv', '__khina.z', 'a.__.rume', 'bai_zzi',
        'dumb_pink6', 'g.xyn_8', 'heenyang___', 'iamsxxy', 'its_suzy_time', 'linhlinhchip', 'lovres_min_', 'seo__0.x',
        'xeoeunx', 'xiianger', 'xx1oo9', 'yaozhuzhu_', '_kkhj2', '_peachme_', 'cheap_box', 'dailyssong', 'dear._.jung',
        'dh_oh_eb', 'eun2ang', 'illl__._', 'kingvivianelee', 'kk.kyl0', 'leedahve', 'lim__bell', 'meowhae_02', 'my._ju',
        's0zzzi', 'sonming52', 'syx_janeyoo', 'yunseul_000', '4._30ark___p', '__mjie__', 'ha.hyunnn',
        'kxxty_070', 'innseinn', 'mo0ndal_', 'moiichanx', '0w0_ji', '5.22__c', 'seolhip', 'soheego',
        'xoeexsol', 'jileeseul', 'mmmcute123', 'sehee2_2', '_scotthh_', 'happyunaaa', 'hmt_beoxx', 'hyxz.xxo',
        'lisiyu2003', 'lexsxxloxn', '_.plo_y', 'tkdboutique', 'yelinnne', 'meowforlili',
        'vina_009i', 'nameisran', 'ju1ys2ven', 'dear__on', 'nanjibeivv', 'k_ch0502', 'ycosag', 'aki1998nana',
        'imparkseoyi', 'g._yng_', 'hiju.73', '875cos', 'for.daon', '64_65_.i', '9530.2', '_chae_rin2', 'crystalgramx',
        'hiyroze', 'honey___bikini', 'seon_h_e', 'sook_0', '0y_joo0', '____gyom', 'c_dbfl', 'guswl_0409', 'kyliett1',
        'laleah2004', 'love.been_', 'luvurse1f_', 'oaoagirl', 'sukimi0320', 'p.___.gj', 'composer_seol', 'egg00_2.0',
        'ju_.vely_', 'lamianxiong7717', 'lylakong01', 'meowsso', 'miwkimin._', 'rlwndud05_', 's2ena2', 'yasminabb_',
        'yuri_luffy', '4rxnge', '_dear_bella_', 'k__xiin', 'sseuldl', 'sstraw_be.rry', 'zav_by1', 'gu__zzzi',
        'hajiwon.22', '3are.ee', 'byhyunbi', 'nanaring_', 'ngquynhnhi_qni', '_wonlyone', 'yvrvxs', 'omao_o1',
        
    ]

    # 1. a_dir의 자식 디렉토리 중, 내부에 파일이 하나도 없는 디렉토리 찾기
    for name in os.listdir(a_dir):
        path = os.path.join(a_dir, name)
        if os.path.isdir(path):
            has_file = False
            for root, dirs, files in os.walk(path):
                if files:
                    has_file = True
                    break

            if not has_file:
                empty_dirs.append(name)

    empty_dirs = [d for d in empty_dirs if d not in pass_dirs]

    # 2. b_dir의 "파일만" 가져오기
    b_files = [
        f for f in os.listdir(b_dir)
        if os.path.isfile(os.path.join(b_dir, f))
    ]

    c_files = [
        f for f in os.listdir(c_dir)
        if os.path.isfile(os.path.join(c_dir, f))
    ]

    # 중복 제거
    all_files = list(set(b_files + c_files))

    # 3. 각 디렉토리 이름으로 시작하는 b_dir 파일 개수 세기
    result = {}
    for d in empty_dirs:
        count = sum(1 for f in all_files if f.startswith(d))
        result[d] = count

    # 4. x개인 디렉토리는 a_dir에서 삭제
    deleted_dirs = []
    for d, count in result.items():
        if count <= DEL_CNT:
            dir_path = os.path.join(a_dir, d)
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                shutil.rmtree(dir_path)
                # print(f"https://www.instagram.com/{d}: {count}")
                deleted_dirs.append(d)

    # 5. 삭제 후 남은 결과만 내림차순 정렬
    filtered_result = {k: v for k, v in result.items() if v > 0}
    sorted_result = sorted(filtered_result.items(), key=lambda x: (-x[1], x[0]))

    # 6. 출력
    for d, count in sorted_result:
        if count <= DEL_CNT:
            print(f"https://www.instagram.com/{d}: {count}")
        else:
            print(f"{d}: {count}")

    low = sorted(
        [(d, count) for d, count in result.items() if count <= DEL_CNT],
        key=lambda x: (-x[1], x[0])
    )
    if low:
        print(f"\nDEL_CNT({DEL_CNT}) 이하 디렉토리:")
        for d, count in low:
            print('\''+d+'\',')

    return dict(sorted_result), deleted_dirs


a = r'\\wsl.localhost\docker-desktop-data\data\docker\volumes\igdata\_data\ig'
b =  r'\\wsl.localhost\docker-desktop-data\data\docker\volumes\igdata\_data\move'
c =  r'\\wsl.localhost\docker-desktop-data\data\docker\volumes\igdata\_data\야짤2024'
count_files_by_empty_dirs(a, b, c)