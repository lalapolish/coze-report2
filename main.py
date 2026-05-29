from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import numpy as np
import io
import requests
from urllib.parse import unquote
import traceback

app = FastAPI(openapi_version="3.0.2")

class FileInput(BaseModel):
    file_url: str 

# =================================================================
# 核心逻辑：按章节划分的函数处理区
# =================================================================

# ----------------- 【第 2 章：发文规模】 -----------------
def get_chapter_2_data(df, target_years):
    temp_df = df.copy()
    temp_df['所属单位'] = temp_df['所属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())
    
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    valid_df = temp_df[temp_df['发表年份'].isin(target_years)]
    unit_table = pd.pivot_table(valid_df, index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    unit_table = unit_table.reset_index()
    
    valid_pattern = '学院|学部|图书馆|研究院|中心'
    unit_table = unit_table[unit_table['所属单位'].str.contains(valid_pattern, na=False)]
    unit_table['total'] = unit_table[target_years].sum(axis=1)
    unit_table = unit_table.sort_values(by='total', ascending=False)
    unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
    
    mapping = {'所属单位': 'unit_name', 2020: 'year_2020', 2021: 'year_2021', 2022: 'year_2022', 2023: 'year_2023', 2024: 'year_2024'}
    unit_table = unit_table.rename(columns=mapping)
    
    return {
        "table_1_trend": {
            "title": "图1 2020-2024年我校人文社科发文量变化",
            "data": trend.to_dict(orient='records')
        },
        "table_2_unit": {
            "title": "表1 2020-2024年我校各学院人文社科发文量统计",
            "data": unit_table[['id', 'unit_name', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']].to_dict(orient='records')
        }
    }

# ----------------- 【第 3 章：发文期刊】 -----------------
def get_chapter_3_data(df, target_years):
    temp_df = df.copy()
    temp_df['所属单位'] = temp_df['所属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())
    
    def clean_level(x):
        x = str(x).upper()
        for lv in ['B', 'C', 'D', 'E', 'F']:
            if lv in x: return f"{lv}级"
        return "其他"

    v3_df = temp_df[temp_df['发表年份'].isin(target_years)].copy()
    v3_df['等级'] = v3_df['学校认定等级'].apply(clean_level)
    target_levels = ['B级', 'C级', 'D级', 'E级', 'F级']

    chart1_pivot = pd.pivot_table(v3_df, index='发表年份', columns='等级', aggfunc='size', fill_value=0)
    for lv in target_levels:
        if lv not in chart1_pivot.columns: chart1_pivot[lv] = 0
    
    chart1 = chart1_pivot[target_levels].reindex(target_years, fill_value=0).reset_index()
    chart1.columns.name = None

    valid_pattern = '学院|学部|图书馆|研究院|中心'
    v3_unit_df = v3_df[v3_df['所属单位'].str.contains(valid_pattern, na=False)]
    
    table1_pivot = pd.pivot_table(v3_unit_df, index='所属单位', columns='等级', aggfunc='size', fill_value=0)
    for lv in target_levels:
        if lv not in table1_pivot.columns: table1_pivot[lv] = 0
    
    table1 = table1_pivot[target_levels].copy()
    table1['总计'] = table1.sum(axis=1)
    table1 = table1.sort_values('总计', ascending=False)
    table1['序号'] = table1['总计'].rank(method='min', ascending=False).astype(int)
    
    top10_table = table1[table1['序号'] <= 10].reset_index()
    cols = ['序号', '所属单位'] + target_levels + ['总计']
    top10_table = top10_table[cols]

    return {
        "chart_1_level_year": {
            "title": "图2 2020-2024年我校人文社科在各等级期刊的发文分布",
            "data": chart1.to_dict(orient='records')
        },
        "table_1_unit_level": {
            "title": "表2 Top10学院在各等级期刊的发文分布",
            "data": top10_table.to_dict(orient='records')
        }
    }

# ----------------- 【第 4 章：基金项目】 -----------------
def get_chapter_4_data(df_long, df_horiz, target_years):
    def parse_year(df, date_col, year_col):
        if date_col in df.columns:
            return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
        return df[year_col] if year_col in df.columns else None

    df_long['year'] = parse_year(df_long, '立项日期', '立项年份')
    df_horiz['year'] = parse_year(df_horiz, '立项日期', '立项年份')
    
    long_v = df_long[df_long['year'].isin(target_years)].copy()
    horiz_v = df_horiz[df_horiz['year'].isin(target_years)].copy()

    # --- 纵向逻辑 ---
    trend_long = long_v.groupby('year').size().reindex(target_years, fill_value=0).reset_index()
    trend_long.columns = ['year', 'count']

    level_dist = long_v['项目级别'].value_counts().reset_index()
    level_dist.columns = ['level', 'count']
    level_dist['ratio'] = (level_dist['count'] / level_dist['count'].sum() * 100).round(2).astype(str) + '%'

    t1_pivot = pd.pivot_table(long_v, index='year', columns='项目级别', aggfunc='size', fill_value=0)
    for c in ['国家级', '省部级']: 
        if c not in t1_pivot.columns: t1_pivot[c] = 0
    t1 = t1_pivot[['国家级', '省部级']].reindex(target_years, fill_value=0).reset_index()
    t1['总计'] = t1['国家级'] + t1['省部级']
    summary_1 = pd.DataFrame([['总计', t1['国家级'].sum(), t1['省部级'].sum(), t1['总计'].sum()]], columns=['year','国家级','省部级','总计'])
    t1_final = pd.concat([t1, summary_1])

    t2_pivot = pd.pivot_table(long_v[long_v['归属单位'].notna()], index='归属单位', columns='year', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in t2_pivot.columns: t2_pivot[y] = 0
    t2_pivot['total'] = t2_pivot.sum(axis=1)
    t2_table = t2_pivot.sort_values('total', ascending=False).head(24).reset_index()
    t2_table.insert(0, '序号', range(1, len(t2_table) + 1))

    rank_dist = long_v['学校等级认定'].value_counts().reset_index()
    rank_dist.columns = ['rank', 'count']
    rank_dist['ratio'] = (rank_dist['count'] / rank_dist['count'].sum() * 100).round(2).astype(str) + '%'

    bins = [0, 20, 40, 60, 80, 100, 120]
    labels = ['(0-20)', '[20-40)', '[40-60)', '[60-80)', '[80-100)', '[100-120]']
    long_v['range'] = pd.cut(long_v['立项经费(万元)'], bins=bins, labels=labels, right=False)
    long_money_dist = long_v['range'].value_counts().reindex(labels, fill_value=0).reset_index()

    top10_money = long_v['立项经费(万元)'].value_counts().head(10).reset_index()
    top10_money.columns = ['经费额', '项目数量']
    top10_money['占比'] = (top10_money['项目数量'] / len(long_v) * 100).round(2).astype(str) + '%'

    t4_pivot = pd.pivot_table(long_v, index='year', columns='项目级别', values='立项经费(万元)', aggfunc='sum', fill_value=0)
    cols4 = ['国际（地区）合作', '国家级', '省部级', '厅局级']
    for c in cols4:
        if c not in t4_pivot.columns: t4_pivot[c] = 0
    t4 = t4_pivot[cols4].reindex(target_years, fill_value=0).reset_index()
    t4['总计（万）'] = t4[cols4].sum(axis=1)
    summary_4 = pd.DataFrame([['总计（万）'] + [t4[c].sum().round(1) for c in cols4 + ['总计（万）']]], columns=['year'] + cols4 + ['总计（万）'])
    t4_final = pd.concat([t4, summary_4]).round(1)

    # --- 横向逻辑 ---
    trend_horiz = horiz_v.groupby('year').size().reindex(target_years, fill_value=0).reset_index()
    trend_horiz.columns = ['year', 'count']
    
    horiz_v['归属单位_clean'] = horiz_v['归属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())
    h_unit_pivot = pd.pivot_table(horiz_v[horiz_v['归属单位_clean'].str.contains('学院|学部|图书馆|研究院|中心', na=False)], 
                                  index='归属单位_clean', columns='year', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in h_unit_pivot.columns: h_unit_pivot[y] = 0
    h_unit_pivot['total'] = h_unit_pivot.sum(axis=1)
    h_unit_table = h_unit_pivot.sort_values('total', ascending=False).head(19).reset_index()

    h_bins = [0, 5, 10, 20, 30, 50, 100, 200, 600]
    h_labels = ['(0-5)', '[5-10)', '[10-20)', '[20-30)', '[30-50)', '[50-100)', '[100-200)', '[200-600)']
    horiz_v['range'] = pd.cut(horiz_v['到账经费'], bins=h_bins, labels=h_labels, right=False)
    horiz_money_dist = horiz_v['range'].value_counts().reindex(h_labels, fill_value=0).reset_index()

    top9_income = horiz_v['到账经费'].value_counts().head(9).reset_index()
    top9_income.columns = ['经费额', '项目数量']
    top9_income['占比'] = (top9_income['项目数量'] / len(horiz_v) * 100).round(2).astype(str) + '%'

    trend_mix = horiz_v.groupby('year').agg({'WID': 'count', '到账经费': 'sum'}).reindex(target_years, fill_value=0).reset_index()

    return {
        "longitudinal": {
            "chart_1": {"title": "图3 2020-2024年我校人文社科纵向项目立项年份分布", "data": trend_long.to_dict(orient='records')},
            "chart_2": {"title": "图4 2020-2024年我校人文社科纵向项目项目级别分布", "data": level_dist.to_dict(orient='records')},
            "table_1": {"title": "表3 2020-2024年纵向项目的年份分布情况（国家级和省部级）", "data": t1_final.to_dict(orient='records')},
            "table_2": {"title": "表4 2020-2024年我校人文社科纵向项目所属单位情况统计（部分）", "data": t2_table.to_dict(orient='records')},
            "chart_3": {"title": "图5 2020-2024年我校人文社科纵向项目学校认定等级情况分布", "data": rank_dist.to_dict(orient='records')},
            "chart_4": {"title": "图6 2020-2024年我校人文社科纵向项目经费情况分布", "data": long_money_dist.to_dict(orient='records')},
            "table_3": {"title": "表5 2020-2024年我校人文社科纵向项目批准经费Top10项目数量统计", "data": top10_money.to_dict(orient='records')},
            "table_4": {"title": "表6 2020-2024年各级人文社科纵向项目经费额度统计表", "data": t4_final.to_dict(orient='records')}
        },
        "horizontal": {
            "chart_4": {"title": "图7 2020-2024年我校人文社科横向项目立项情况年份统计", "data": trend_horiz.to_dict(orient='records')},
            "table_5": {"title": "表7 2020-2024年我校人文社科横向项目所属单位统计（部分）", "data": h_unit_table.to_dict(orient='records')},
            "chart_5": {"title": "图8 2020-2024年我校人文社科横向项目到帐经费情况统计", "data": horiz_money_dist.to_dict(orient='records')},
            "table_6": {"title": "表8 2020-2024年我校人文社科横向项目到帐经费数量Top9统计", "data": top9_income.to_dict(orient='records')},
            "chart_6": {"title": "图9 我校人文社科横向项目各年项目数量和到账经费趋势图", "data": trend_mix.to_dict(orient='records')}
        }
    }

# ----------------- 【第 5 章：重要学者 - 第一部分：论文】 -----------------
def get_chapter_5_paper_part(df, target_years):
    v5_df = df[df['发表年份'].isin(target_years)].copy()
    def clean_level(x):
        x = str(x).upper()
        for lv in ['B', 'C', 'D', 'E', 'F']:
            if lv in x: return f"{lv}级"
        return "其他"
    v5_df['等级'] = v5_df['学校认定等级'].apply(clean_level)
    target_levels = ['B级', 'C级', 'D级', 'E级', 'F级']

    paper_stats = pd.pivot_table(v5_df, index=['作者姓名', '所属单位'], columns='等级', aggfunc='size', fill_value=0)
    for lv in target_levels:
        if lv not in paper_stats.columns: paper_stats[lv] = 0
    paper_stats['总计'] = paper_stats[target_levels].sum(axis=1)

    # 表 9
    table_9 = paper_stats[paper_stats['总计'] >= 15].sort_values('总计', ascending=False).reset_index()
    table_9 = table_9[['作者姓名'] + target_levels + ['总计', '所属单位']]

    # 表 10 (B/C级分布)
    b_list = paper_stats[paper_stats['B级'] >= 4].sort_values('B级', ascending=False).reset_index()[['作者姓名', 'B级', '所属单位']].rename(columns={'B级': '发文数量'}).to_dict(orient='records')
    c_list = paper_stats[paper_stats['C级'] >= 4].sort_values('C级', ascending=False).reset_index()[['作者姓名', 'C级', '所属单位']].rename(columns={'C级': '发文数量'}).to_dict(orient='records')

    return {
        "table_1_important_scholars": {
            "title": "表9 我校人文社会科学重要学者（按照总发文数量）",
            "data": table_9.to_dict(orient='records')
        },
        "table_2_high_level_scholars": {
            "title": "表10 我校人文社会科学重要学者（根据学校认定等级）",
            "data": {"B_level_above_4": b_list, "C_level_above_4": c_list}
        }
    }

# ----------------- 【第 5 章：重要学者 - 第二部分：项目】 -----------------
def get_chapter_5_project_part(df_long, df_horiz, target_years):
    def parse_year(df, date_col, year_col):
        if date_col in df.columns:
            return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
        return df[year_col] if year_col in df.columns else None

    df_long['year'] = parse_year(df_long, '立项日期', '立项年份')
    df_horiz['year'] = parse_year(df_horiz, '立项日期', '立项年份')
    long_v = df_long[df_long['year'].isin(target_years)].copy()
    horiz_v = df_horiz[df_horiz['year'].isin(target_years)].copy()

    # 表 11
    v_stats = long_v.groupby('负责人').size().reset_index(name='立项数量')
    table_11 = v_stats[v_stats['立项数量'] >= 5].sort_values('立项数量', ascending=False).reset_index(drop=True)
    table_11.insert(0, '序号', range(1, len(table_11) + 1))

    # 表 12
    nat_stats = long_v[long_v['项目级别'].str.contains('国家级', na=False)].groupby(['负责人', '归属单位']).size().reset_index(name='项目数量')
    prov_stats = long_v[long_v['项目级别'].str.contains('省部级', na=False)].groupby(['负责人', '归属单位']).size().reset_index(name='项目数量')
    
    # 表 13
    table_13 = horiz_v.groupby('项目负责人').size().reset_index(name='立项数量')
    table_13 = table_13[table_13['立项数量'] >= 5].sort_values('立项数量', ascending=False).reset_index(drop=True)
    table_13.insert(0, '序号', range(1, len(table_13) + 1))

    # 表 14
    h_money_stats = horiz_v.groupby('项目负责人').agg({'到账经费': 'sum', 'WID': 'count'}).reset_index()
    h_money_stats.columns = ['项目负责人', '到账经费（万元）', '立项数量']
    table_14 = h_money_stats[h_money_stats['到账经费（万元）'] > 120].sort_values('到账经费（万元）', ascending=False).reset_index(drop=True)
    table_14.insert(0, '序号', range(1, len(table_14) + 1))

    return {
        "table_3_vertical_top": {
            "title": "表11 2020-2024年我校人文社科纵向项目立项数5项及以上的学者",
            "data": table_11.to_dict(orient='records')
        },
        "table_4_national_provincial": {
            "title": "表12 我校人文社会科学国家级和省部级项目重要学者",
            "data": {
                "national_above_2": nat_stats[nat_stats['项目数量'] >= 2].to_dict(orient='records'),
                "provincial_above_3": prov_stats[prov_stats['项目数量'] >= 3].to_dict(orient='records')
            }
        },
        "table_5_horizontal_top": {
            "title": "表13 2020-2024年我校人文社科横向项目立项数5项及以上的学者",
            "data": table_13.to_dict(orient='records')
        },
        "table_6_horizontal_money": {
            "title": "表14 2020-2024年我校人文社科横向项目经费超过120万的学者立项情况",
            "data": table_14.to_dict(orient='records')
        }
    }

# ----------------- 【第 6 章：专著】 -----------------
def get_chapter_6_data(df, target_years):
    temp_df = df.copy()
    temp_df['所属单位'] = temp_df['所属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())
    
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    unit_table = pd.pivot_table(temp_df[temp_df['发表年份'].isin(target_years)], index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    unit_table = unit_table.reset_index()
    unit_table = unit_table[unit_table['所属单位'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    unit_table['total'] = unit_table[target_years].sum(axis=1)
    unit_table = unit_table.sort_values(by='total', ascending=False)
    unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
    
    return {
        "table_1_trend": {
            "title": "图10 2020-2024年我校人文社科著作出版数量年度变化",
            "data": trend.to_dict(orient='records')
        },
        "table_2_unit": {
            "title": "表15 2020-2024年我校各学院人文社科著作出版量年度变化",
            "data": unit_table.to_dict(orient='records')
        }
    }

# ----------------- 【第 7 章：获奖情况】 -----------------
def get_chapter_7_data(df, target_years):
    temp_df = df.copy()
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    def normalize_level(x):
        x = str(x).strip().upper()
        for letter in ['A', 'B', 'C', 'D', 'E', 'F']:
            if letter in x: return f"{letter}级"
        return '其他'

    valid_df = temp_df[temp_df['发表年份'].isin(target_years)].copy()
    valid_df['等级'] = valid_df['学校认定等级'].apply(normalize_level)
    dist_table = pd.pivot_table(valid_df, index='发表年份', columns='等级', aggfunc='size', fill_value=0)
    for lv in ['A级', 'B级', 'C级', 'D级', 'E级', 'F级']:
        if lv not in dist_table.columns: dist_table[lv] = 0
    dist_table = dist_table.reindex(target_years, fill_value=0).reset_index()

    return {
        "table_1_trend": {
            "title": "图11 2020-2024年我校人文社科获奖数量变化",
            "data": trend.to_dict(orient='records')
        },
        "table_2_level_dist": {
            "title": "图12 我校人文社科各等级的获奖分布",
            "data": dist_table.to_dict(orient='records')
        }
    }


# =================================================================
# 主接口
# =================================================================

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        file_name = unquote(input.file_url.split('/')[-1])
        response = requests.get(input.file_url)
        content = io.BytesIO(response.content)
        target_years = [2020, 2021, 2022, 2023, 2024]

        # 1. 识别：基金项目
        if "项目" in file_name or "课题" in file_name:
            sheets = pd.read_excel(content, sheet_name=None)
            s_names = list(sheets.keys())
            df_long = sheets[s_names[0]]
            df_horiz = sheets[s_names[1]] if len(s_names) > 1 else pd.DataFrame()
            return {
                "status": "success", 
                "data": {
                    "chapter_4": get_chapter_4_data(df_long, df_horiz, target_years),
                    "chapter_5_part2": get_chapter_5_project_part(df_long, df_horiz, target_years)
                }
            }

        # 2. 识别：单表
        df = pd.read_excel(content, sheet_name=0)
        df.columns = df.columns.str.strip()
        if '获奖日期' in df.columns:
            df['发表年份'] = pd.to_datetime(df['获奖日期'], errors='coerce').dt.year
        elif '出版时间' in df.columns:
            df['发表年份'] = pd.to_datetime(df['出版时间'], errors='coerce').dt.year
        elif '发表年份' in df.columns:
            df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')

        result_data = {}
        if "论文" in file_name:
            result_data["chapter_2"] = get_chapter_2_data(df, target_years)
            result_data["chapter_3"] = get_chapter_3_data(df, target_years)
            result_data["chapter_5_part1"] = get_chapter_5_paper_part(df, target_years)
        elif "专著" in file_name:
            result_data["chapter_6"] = get_chapter_6_data(df, target_years)
        elif "获奖" in file_name:
            result_data["chapter_7"] = get_chapter_7_data(df, target_years)
        else:
            return {"status": "warning", "message": f"文件名 [{file_name}] 未匹配到业务表"}

        return {"status": "success", "data": result_data}

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
