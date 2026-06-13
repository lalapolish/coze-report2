from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
import pandas as pd
import numpy as np
import io
import requests
from urllib.parse import unquote
import traceback

app = FastAPI(openapi_version="3.0.2")

# 修改输入模型，支持链接列表
class FileInput(BaseModel):
    file_urls: List[str] 

# =================================================================
# 核心逻辑：章节数据处理函数
# =================================================================

def get_chapter_2_data(df, target_years):
    temp_df = df.copy()
    temp_df['所属单位'] = temp_df['所属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['publish_year', 'count']
    
    valid_df = temp_df[temp_df['发表年份'].isin(target_years)]
    unit_table = pd.pivot_table(valid_df, index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    unit_table = unit_table.reset_index()
    unit_table = unit_table[unit_table['所属单位'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    unit_table['total'] = unit_table[target_years].sum(axis=1)
    unit_table = unit_table.sort_values(by='total', ascending=False)
    unit_table.insert(0, 'index_no', range(1, len(unit_table) + 1))
    
    mapping = {'所属单位': 'affiliation', 2020: 'year_2020', 2021: 'year_2021', 2022: 'year_2022', 2023: 'year_2023', 2024: 'year_2024', 'total': 'total'}
    unit_table = unit_table.rename(columns=mapping)
    return {
        "table_1_trend": {"title": "图1 2020-2024年我校人文社科发文量变化", "data": trend.to_dict(orient='records')},
        "table_2_unit": {"title": "表1 2020-2024年我校各学院人文社科发文量统计", "data": unit_table[['index_no', 'affiliation', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']].to_dict(orient='records')}
    }

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
    level_mapping = {'B级': 'level_B', 'C级': 'level_C', 'D级': 'level_D', 'E级': 'level_E', 'F级': 'level_F', '其他': 'others'}
    
    chart1_pivot = pd.pivot_table(v3_df, index='发表年份', columns='等级', aggfunc='size', fill_value=0)
    for lv in target_levels:
        if lv not in chart1_pivot.columns: chart1_pivot[lv] = 0
    chart1 = chart1_pivot[target_levels].reindex(target_years, fill_value=0).reset_index()
    chart1.rename(columns={'发表年份': 'publish_year', **level_mapping}, inplace=True)

    v3_unit_df = v3_df[v3_df['所属单位'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    table1_pivot = pd.pivot_table(v3_unit_df, index='所属单位', columns='等级', aggfunc='size', fill_value=0)
    for lv in target_levels:
        if lv not in table1_pivot.columns: table1_pivot[lv] = 0
    table1 = table1_pivot[target_levels].copy()
    table1['总计'] = table1.sum(axis=1)
    table1 = table1.sort_values('总计', ascending=False)
    table1['序号'] = table1['总计'].rank(method='min', ascending=False).astype(int)
    top10_table = table1[table1['序号'] <= 10].reset_index()
    top10_table.rename(columns={'序号': 'index_no', '所属单位': 'affiliation', '总计': 'total', **level_mapping}, inplace=True)
    
    return {
        "chart_1_level_year": {"title": "图2 2020-2024年我校人文社科在各等级期刊的发文分布", "data": chart1.to_dict(orient='records')},
        "table_1_unit_level": {"title": "表2 Top10学院在各等级期刊的发文分布", "data": top10_table.to_dict(orient='records')}
    }

def get_chapter_4_data(df_long, df_horiz, target_years):
    def parse_year(df, date_col, year_col):
        if date_col in df.columns:
            return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
        return df[year_col] if year_col in df.columns else None

    df_long['year'] = parse_year(df_long, '立项日期', '立项年份')
    df_horiz['year'] = parse_year(df_horiz, '立项日期', '立项年份')
    long_v = df_long[df_long['year'].isin(target_years)].copy()
    horiz_v = df_horiz[df_horiz['year'].isin(target_years)].copy()

    trend_long = long_v.groupby('year').size().reindex(target_years, fill_value=0).reset_index()
    trend_long.columns = ['publish_year', 'count']

    level_dist = long_v['项目级别'].value_counts().reset_index()
    level_dist.columns = ['project_rank', 'count']

    t1_pivot = pd.pivot_table(long_v, index='year', columns='项目级别', aggfunc='size', fill_value=0)
    for c in ['国家级', '省部级']: 
        if c not in t1_pivot.columns: t1_pivot[c] = 0
    t1 = t1_pivot[['国家级', '省部级']].reindex(target_years, fill_value=0).reset_index()
    t1['总计'] = t1['国家级'] + t1['省部级']
    t1.rename(columns={'year': 'publish_year', '国家级': 'national_level', '省部级': 'provincial_level', '总计': 'total'}, inplace=True)

    t2_pivot = pd.pivot_table(long_v[long_v['归属单位'].notna()], index='归属单位', columns='year', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in t2_pivot.columns: t2_pivot[y] = 0
    t2_table = t2_pivot.assign(total=t2_pivot.sum(axis=1)).sort_values('total', ascending=False).head(24).reset_index()
    t2_table.insert(0, 'index_no', range(1, len(t2_table) + 1))
    t2_table.rename(columns={'归属单位': 'department', 'total': 'total'}, inplace=True)

    rank_dist = long_v['学校等级认定'].value_counts().reset_index()
    rank_dist.columns = ['school_rating', 'count']
    rank_dist['percentage'] = (rank_dist['count'] / rank_dist['count'].sum() * 100).round(2)

    long_v['range'] = pd.cut(long_v['立项经费(万元)'], bins=[0, 20, 40, 60, 80, 100, 120], labels=['(0-20)', '[20-40)', '[40-60)', '[60-80)', '[80-100)', '[100-120]'], right=False)
    long_money_dist = long_v['range'].value_counts().sort_index().reset_index()
    long_money_dist.columns = ['others', 'count']

    top10_money = long_v['立项经费(万元)'].value_counts().head(10).reset_index()
    top10_money.columns = ['received_funding', 'project_count']
    top10_money.insert(0, 'index_no', range(1, len(top10_money) + 1))
    top10_money['percentage'] = (top10_money['project_count'] / top10_money['project_count'].sum() * 100).round(2)

    t4_pivot = pd.pivot_table(long_v, index='year', columns='项目级别', values='立项经费(万元)', aggfunc='sum', fill_value=0)
    target_cols = ['国际（地区）合作', '国家级', '省部级', '厅局级']
    for c in target_cols:
        if c not in t4_pivot.columns: t4_pivot[c] = 0
    t4 = t4_pivot[target_cols].reindex(target_years, fill_value=0).reset_index()
    t4.rename(columns={'year': 'publish_year', '国际（地区）合作': 'international_cooperation', '国家级': 'national_level', '省部级': 'provincial_level', '厅局级': 'bureau_level'}, inplace=True)
    t4['total'] = t4[['international_cooperation', 'national_level', 'provincial_level', 'bureau_level']].sum(axis=1)
    t4 = t4.round(1)

    trend_horiz = horiz_v.groupby('year').size().reindex(target_years, fill_value=0).reset_index()
    trend_horiz.columns = ['publish_year', 'count']

    horiz_v['归属单位_clean'] = horiz_v['归属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())
    h_unit_pivot = pd.pivot_table(horiz_v[horiz_v['归属单位_clean'].str.contains('学院|学部|图书馆|研究院|中心', na=False)], index='归属单位_clean', columns='year', aggfunc='size', fill_value=0)
    h_unit_table = h_unit_pivot.assign(total=h_unit_pivot.sum(axis=1)).sort_values('total', ascending=False).head(19).reset_index()
    h_unit_table.insert(0, 'index_no', range(1, len(h_unit_table) + 1))
    h_unit_table.rename(columns={'归属单位_clean': 'department_clean', 'total': 'total'}, inplace=True)

    horiz_money_dist_raw = pd.cut(horiz_v['到账经费'], bins=[0, 5, 10, 20, 30, 50, 100, 200, 600], labels=['(0-5)', '[5-10)', '[10-20)', '[20-30)', '[30-50)', '[50-100)', '[100-200)', '[200-600)'], right=False)
    horiz_money_dist = horiz_money_dist_raw.value_counts().sort_index().reset_index()
    horiz_money_dist.columns = ['others', 'count']

    top9_income = horiz_v['到账经费'].value_counts().head(9).reset_index()
    top9_income.columns = ['received_funding', 'project_count']
    top9_income.insert(0, 'index_no', range(1, len(top9_income) + 1))
    top9_income['percentage'] = (top9_income['project_count'] / top9_income['project_count'].sum() * 100).round(2)

    trend_mix = horiz_v.groupby('year').agg({'WID': 'count', '到账经费': 'sum'}).reindex(target_years, fill_value=0).reset_index()
    trend_mix.columns = ['publish_year', 'project_count', 'received_funding']

    return {
        "longitudinal": {
            "chart_1": {"title": "图3 2020-2024年我校人文社科纵向项目立项年份分布", "data": trend_long.to_dict(orient='records')},
            "chart_2": {"title": "图4 2020-2024年我校人文社科纵向项目项目级别分布", "data": level_dist.to_dict(orient='records')},
            "table_1": {"title": "表3 2020-2024年纵向项目的年份分布情况（国家级和省部级）", "data": t1.to_dict(orient='records')},
            "table_2": {"title": "表4 2020-2024年我校人文社科纵向项目所属单位情况统计（部分）", "data": t2_table.to_dict(orient='records')},
            "chart_3": {"title": "图5 2020-2024年我校人文社科纵向项目学校认定等级情况分布", "data": rank_dist.to_dict(orient='records')},
            "chart_4": {"title": "图6 2020-2024年我校人文社科纵向项目经费情况分布", "data": long_money_dist.to_dict(orient='records')},
            "table_3": {"title": "表5 2020-2024年我校人文社科纵向项目批准经费Top10项目数量统计", "data": top10_money.to_dict(orient='records')},
            "table_4": {"title": "表6 2020-2024年各级人文社科纵向项目经费额度统计表", "data": t4.to_dict(orient='records')}
        },
        "horizontal": {
            "chart_4": {"title": "图7 2020-2024年我校人文社科横向项目立项情况年份统计", "data": trend_horiz.to_dict(orient='records')},
            "table_5": {"title": "表7 2020-2024年我校人文社科横向项目所属单位统计（部分）", "data": h_unit_table.to_dict(orient='records')},
            "chart_5": {"title": "图8 2020-2024年我校人文社科横向项目到帐经费情况统计", "data": horiz_money_dist.to_dict(orient='records')},
            "table_6": {"title": "表8 2020-2024年我校人文社科横向项目到帐经费数量Top9统计", "data": top9_income.to_dict(orient='records')},
            "chart_6": {"title": "图9 我校人文社科横向项目各年项目数量和到账经费趋势图", "data": trend_mix.to_dict(orient='records')}
        }
    }

def get_chapter_5_paper_part(df, target_years):
    v5_df = df[df['发表年份'].isin(target_years)].copy()
    def clean_level(x):
        x = str(x).upper()
        for lv in ['B', 'C', 'D', 'E', 'F']:
            if lv in x: return f"{lv}级"
        return "其他"
    v5_df['等级'] = v5_df['学校认定等级'].apply(clean_level)
    paper_stats = pd.pivot_table(v5_df, index=['作者姓名', '所属单位'], columns='等级', aggfunc='size', fill_value=0)
    for lv in ['B级', 'C级', 'D级', 'E级', 'F级']:
        if lv not in paper_stats.columns: paper_stats[lv] = 0
    paper_stats['总计'] = paper_stats[['B级', 'C级', 'D级', 'E级', 'F级']].sum(axis=1)
    
    level_mapping = {'B级': 'level_B', 'C级': 'level_C', 'D级': 'level_D', 'E级': 'level_E', 'F级': 'level_F', '总计': 'total'}
    table_9 = paper_stats[paper_stats['总计'] >= 15].sort_values('总计', ascending=False).reset_index()
    table_9.rename(columns={'作者姓名': 'author_name', '所属单位': 'affiliation', **level_mapping}, inplace=True)
    b_list = paper_stats[paper_stats['B级'] >= 4].sort_values('B级', ascending=False).reset_index()
    b_list.rename(columns={'作者姓名': 'author_name', '所属单位': 'affiliation', **level_mapping}, inplace=True)
    c_list = paper_stats[paper_stats['C级'] >= 4].sort_values('C级', ascending=False).reset_index()
    c_list.rename(columns={'作者姓名': 'author_name', '所属单位': 'affiliation', **level_mapping}, inplace=True)
    
    return {
        "table_1_important_scholars": {"title": "表9 我校人文社会科学重要学者（按照总发文数量）", "data": table_9.to_dict(orient='records')},
        "table_2_high_level_scholars": {"title": "表10 我校人文社会科学重要学者（根据学校认定等级）", "data": {"B_level_above_4": b_list.to_dict(orient='records'), "C_level_above_4": c_list.to_dict(orient='records')}}
    }

def get_chapter_5_project_part(df_long, df_horiz, target_years):
    def parse_year(df, date_col, year_col):
        if date_col in df.columns:
            return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
        return df[year_col] if year_col in df.columns else None
    df_long['year'] = parse_year(df_long, '立项日期', '立项年份')
    df_horiz['year'] = parse_year(df_horiz, '立项日期', '立项年份')
    long_v = df_long[df_long['year'].isin(target_years)].copy()
    horiz_v = df_horiz[df_horiz['year'].isin(target_years)].copy()
    
    v_stats = long_v.groupby('负责人').size().reset_index(name='立项数量')
    table_11 = v_stats[v_stats['立项数量'] >= 5].sort_values('立项数量', ascending=False).reset_index(drop=True)
    table_11.rename(columns={'负责人': 'manager', '立项数量': 'project_count'}, inplace=True)
    
    nat_stats = long_v[long_v['项目级别'].str.contains('国家级', na=False)].groupby(['负责人', '归属单位']).size().reset_index(name='项目数量')
    nat_stats.rename(columns={'负责人': 'manager', '归属单位': 'department', '项目数量': 'num_projects'}, inplace=True)
    
    prov_stats = long_v[long_v['项目级别'].str.contains('省部级', na=False)].groupby(['负责人', '归属单位']).size().reset_index(name='项目数量')
    prov_stats.rename(columns={'负责人': 'manager', '归属单位': 'department', '项目数量': 'num_projects'}, inplace=True)
    
    h_stats = horiz_v.groupby('项目负责人').size().reset_index(name='立项数量')
    table_13 = h_stats[h_stats['立项数量'] >= 5].sort_values('立项数量', ascending=False).reset_index(drop=True)
    table_13.rename(columns={'项目负责人': 'project_leader', '立项数量': 'project_count'}, inplace=True)
    
    h_money_stats = horiz_v.groupby('项目负责人').agg({'到账经费': 'sum', 'WID': 'count'}).reset_index()
    table_14 = h_money_stats[h_money_stats['到账经费'] > 120].sort_values('到账经费', ascending=False).reset_index(drop=True)
    table_14.rename(columns={'项目负责人': 'project_leader', '到账经费': 'received_funding', 'WID': 'project_count'}, inplace=True)
    
    return {
        "table_3_vertical_top": {"title": "表11 2020-2024年我校人文社科纵向项目立项数5项及以上的学者", "data": table_11.to_dict(orient='records')},
        "table_4_national_provincial": {"title": "表12 我校人文社会科学国家级和省部级项目重要学者", "data": {"national_above_2": nat_stats[nat_stats['num_projects'] >= 2].to_dict(orient='records'), "provincial_above_3": prov_stats[prov_stats['num_projects'] >= 3].to_dict(orient='records')}},
        "table_5_horizontal_top": {"title": "表13 2020-2024年我校人文社科横向项目立项数5项及以上的学者", "data": table_13.to_dict(orient='records')},
        "table_6_horizontal_money": {"title": "表14 2020-2024年我校人文社科横向项目经费超过120万的学者立项情况", "data": table_14.to_dict(orient='records')}
    }

def get_chapter_6_data(df, target_years):
    temp_df = df.copy()
    temp_df['所属单位'] = temp_df['所属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['publish_year', 'count']
    
    unit_table = pd.pivot_table(temp_df[temp_df['发表年份'].isin(target_years)], index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    unit_table = unit_table.reset_index()
    unit_table = unit_table[unit_table['所属单位'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    unit_table['total'] = unit_table[target_years].sum(axis=1)
    unit_table = unit_table.sort_values(by='total', ascending=False)
    unit_table.rename(columns={'所属单位': 'affiliation', 'total': 'total'}, inplace=True)
    return {
        "table_1_trend": {"title": "图10 2020-2024年我校人文社科著作出版数量年度变化", "data": trend.to_dict(orient='records')},
        "table_2_unit": {"title": "表15 2020-2024年我校各学院人文社科著作出版量年度变化", "data": unit_table.to_dict(orient='records')}
    }

def get_chapter_7_data(df, target_years):
    temp_df = df.copy()
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['publish_year', 'count']
    
    def normalize_level(x):
        x = str(x).strip().upper()
        for letter in ['A', 'B', 'C', 'D', 'E', 'F']:
            if letter in x: return f"{letter}级"
        return '其他'
    valid_df = temp_df[temp_df['发表年份'].isin(target_years)].copy()
    valid_df['等级'] = valid_df['学校认定等级'].apply(normalize_level)
    dist_table = pd.pivot_table(valid_df, index='发表年份', columns='等级', aggfunc='size', fill_value=0)
    lv_cols = ['A级', 'B级', 'C级', 'D级', 'E级', 'F级']
    lv_mapping = {'A级': 'level_A', 'B级': 'level_B', 'C级': 'level_C', 'D级': 'level_D', 'E级': 'level_E', 'F级': 'level_F'}
    for lv in lv_cols:
        if lv not in dist_table.columns: dist_table[lv] = 0
    dist_table = dist_table.reindex(target_years, fill_value=0).reset_index()
    dist_table.rename(columns={'发表年份': 'publish_year', **lv_mapping}, inplace=True)
    return {
        "table_1_trend": {"title": "图11 2020-2024年我校人文社科获奖数量变化", "data": trend.to_dict(orient='records')},
        "table_2_level_dist": {"title": "图12 我校人文社科各等级的获奖分布", "data": dist_table.to_dict(orient='records')}
    }

def get_chapter_8_summary(ch1_data: Dict[str, Any]) -> Dict[str, Any]:
    long_total = ch1_data.get("long_f", 0)
    nat_count = ch1_data.get("long_national_count", 0)
    nat_pct = round((nat_count / long_total * 100), 2) if long_total > 0 else 0
    return {
        "conclusions": {
            "paper_part": f"2020-2024年总发文{ch1_data.get('paper_f')}篇，年均{round(ch1_data.get('paper_f',0)/5,1)}篇。",
            "project_part": f"纵向项目共{long_total}项，其中国家级占比{nat_pct}%。横向项目总经费达{ch1_data.get('horiz_money_total', 0)}万元。",
            "scholar_part": "形成了高产出学者群，但在青年人才梯队建设上仍有空间。",
            "book_award_part": f"专著出版稳步提升。获奖共{ch1_data.get('award_total')}项。"
        },
        "suggestions": [
            "实施‘高峰学科’质量跃升计划，对B级以上期刊发表进行定点激励。",
            "优化国家级课题申报辅导机制。",
            "针对横向经费分布不均现状，鼓励跨学科咨询合作。",
            "设立‘重大成果培育库’。"
        ],
        "raw_metrics": ch1_data 
    }

# =================================================================
# 新增并修复：附录数据统计函数 (已修复Key对应关系)
# =================================================================

def get_appendix_data(df_paper, df_long, df_horiz, target_years):
    # 统一重命名映射，确保对应 Coze 定义的英文变量
    year_map = {y: f"y{y}" for y in target_years}
    common_map = {"所属单位": "unit", "归属单位": "unit", "总计": "total"}
    level_map = {"B级": "lv_B", "C级": "lv_C", "D级": "lv_D", "E级": "lv_E", "F级": "lv_F"}

    # 1. 附表2-1 论文年份分布
    if not df_paper.empty:
        df_p = df_paper.copy()
        df_p['所属单位'] = df_p['所属单位'].fillna('未知单位')
        ap_2_1 = pd.pivot_table(df_p[df_p['发表年份'].isin(target_years)], index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
        for y in target_years:
            if y not in ap_2_1.columns: ap_2_1[y] = 0
        ap_2_1 = ap_2_1[target_years].reset_index()
        ap_2_1['总计'] = ap_2_1[target_years].sum(axis=1)
        # 执行重命名：年份转y2020，中转英
        ap_2_1 = ap_2_1.rename(columns={**year_map, **common_map})
        data_2_1 = ap_2_1.to_dict(orient='records')
    else: data_2_1 = []

    # 2. 附表3-1 论文等级分布
    if not df_paper.empty:
        df_p3 = df_paper.copy()
        def clean_level_ap(x):
            x = str(x).upper()
            for lv in ['B', 'C', 'D', 'E', 'F']:
                if lv in x: return f"{lv}级"
            return "其他"
        df_p3['等级'] = df_p3['学校认定等级'].apply(clean_level_ap)
        ap_3_1 = pd.pivot_table(df_p3[df_p3['发表年份'].isin(target_years)], index='所属单位', columns='等级', aggfunc='size', fill_value=0)
        target_levels = ['B级', 'C级', 'D级', 'E级', 'F级']
        for lv in target_levels:
            if lv not in ap_3_1.columns: ap_3_1[lv] = 0
        ap_3_1 = ap_3_1[target_levels].reset_index()
        ap_3_1['总计'] = ap_3_1[target_levels].sum(axis=1)
        # 执行重命名：等级转lv_B，中转英
        ap_3_1 = ap_3_1.rename(columns={**level_map, **common_map})
        data_3_1 = ap_3_1.to_dict(orient='records')
    else: data_3_1 = []

    # 3. 附表4-1 纵向项目年份分布
    if not df_long.empty:
        ap_4_1 = pd.pivot_table(df_long[df_long['temp_year'].isin(target_years)], index='归属单位', columns='temp_year', aggfunc='size', fill_value=0)
        for y in target_years:
            if y not in ap_4_1.columns: ap_4_1[y] = 0
        ap_4_1 = ap_4_1[target_years].reset_index()
        ap_4_1['总计'] = ap_4_1[target_years].sum(axis=1)
        # 执行重命名
        ap_4_1 = ap_4_1.rename(columns={**year_map, **common_map})
        data_4_1 = ap_4_1.to_dict(orient='records')
    else: data_4_1 = []

    # 4. 附表4-2 横向项目年份分布
    if not df_horiz.empty:
        ap_4_2 = pd.pivot_table(df_horiz[df_horiz['temp_year'].isin(target_years)], index='归属单位', columns='temp_year', aggfunc='size', fill_value=0)
        for y in target_years:
            if y not in ap_4_2.columns: ap_4_2[y] = 0
        ap_4_2 = ap_4_2[target_years].reset_index()
        ap_4_2['总计'] = ap_4_2[target_years].sum(axis=1)
        # 执行重命名
        ap_4_2 = ap_4_2.rename(columns={**year_map, **common_map})
        data_4_2 = ap_4_2.to_dict(orient='records')
    else: data_4_2 = []

    return {
        "appendix_2_1": {"title": "附表2-1 2020-2024我校各单位发文分布", "data": data_2_1},
        "appendix_3_1": {"title": "附表3-1 2020-2024我校各单位在各等级期刊的发文分布", "data": data_3_1},
        "appendix_4_1": {"title": "附表4-1 2020-2024年我校各单位纵向项目立项数量", "data": data_4_1},
        "appendix_4_2": {"title": "附表4-2 2020-2024年我校各单位横向项目立项数量", "data": data_4_2}
    }

# =================================================================
# 主函数入口
# =================================================================

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    combined_data = {
        "chapter_2_3_5p1": {}, 
        "chapter_4_5p2": {},   
        "chapter_6": {},       
        "chapter_7": {},
        "chapter_8": {},
        "appendix": {} # 附录
    }
    
    ch1_summary = {
        "paper_f": 0, "horiz_f": 0, "long_f": 0, 
        "book_20_23": 0, "book_24": 0, "award_total": 0,
        "long_national_count": 0, "horiz_money_total": 0,
        "award_a_count": 0, "award_b_count": 0
    }

    # 用于暂存各文件DF以便生成附录
    df_paper_final = pd.DataFrame()
    df_long_final = pd.DataFrame()
    df_horiz_final = pd.DataFrame()

    try:
        target_years = [2020, 2021, 2022, 2023, 2024]
        for url in input.file_urls:
            file_name = unquote(url.split('/')[-1])
            response = requests.get(url)
            content = io.BytesIO(response.content)

            if "项目" in file_name or "课题" in file_name:
                sheets = pd.read_excel(content, sheet_name=None)
                s_names = list(sheets.keys())
                df_long = sheets[s_names[0]]
                df_horiz = sheets[s_names[1]] if len(s_names) > 1 else pd.DataFrame()
                
                def parse_year_internal(df, date_col, year_col):
                    if date_col in df.columns:
                        return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
                    return df[year_col] if year_col in df.columns else None
                
                df_long['temp_year'] = parse_year_internal(df_long, '立项日期', '立项年份')
                df_horiz['temp_year'] = parse_year_internal(df_horiz, '立项日期', '立项年份')
                
                df_long_final = df_long.copy()
                df_horiz_final = df_horiz.copy()

                valid_long = df_long[df_long['temp_year'].isin(target_years)]
                ch1_summary["long_f"] = len(valid_long)
                ch1_summary["long_national_count"] = len(valid_long[valid_long['项目级别'].str.contains('国家级', na=False)])
                
                valid_horiz = df_horiz[df_horiz['temp_year'].isin(target_years)]
                ch1_summary["horiz_f"] = len(valid_horiz)
                ch1_summary["horiz_money_total"] = round(valid_horiz['到账经费'].sum(), 2)

                combined_data["chapter_4_5p2"] = {
                    "chapter_4": get_chapter_4_data(df_long, df_horiz, target_years),
                    "chapter_5_part2": get_chapter_5_project_part(df_long, df_horiz, target_years)
                }
            else:
                df = pd.read_excel(content, sheet_name=0)
                df.columns = df.columns.str.strip()
                if '获奖日期' in df.columns:
                    df['发表年份'] = pd.to_datetime(df['获奖日期'], errors='coerce').dt.year
                elif '出版时间' in df.columns:
                    df['发表年份'] = pd.to_datetime(df['出版时间'], errors='coerce').dt.year
                elif '发表年份' in df.columns:
                    df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')

                if "论文" in file_name:
                    df_paper_final = df.copy()
                    ch1_summary["paper_f"] = len(df[df['发表年份'].isin(target_years)])
                    combined_data["chapter_2_3_5p1"] = {
                        "chapter_2": get_chapter_2_data(df, target_years),
                        "chapter_3": get_chapter_3_data(df, target_years),
                        "chapter_5_part1": get_chapter_5_paper_part(df, target_years)
                    }
                elif "专著" in file_name:
                    v6_df = df[df['发表年份'].isin(target_years)]
                    ch1_summary["book_20_23"] = len(v6_df[v6_df['发表年份'].isin([2020, 2021, 2022, 2023])])
                    ch1_summary["book_24"] = len(v6_df[v6_df['发表年份'] == 2024])
                    combined_data["chapter_6"] = get_chapter_6_data(df, target_years)
                elif "获奖" in file_name:
                    v7_df = df[df['发表年份'].isin(target_years)]
                    ch1_summary["award_total"] = len(v7_df)
                    ch1_summary["award_a_count"] = len(v7_df[v7_df['学校认定等级'].str.contains('A', na=False, case=False)])
                    ch1_summary["award_b_count"] = len(v7_df[v7_df['学校认定等级'].str.contains('B', na=False, case=False)])
                    combined_data["chapter_7"] = get_chapter_7_data(df, target_years)

        # 聚合生成 8 章
        combined_data["chapter_8"] = get_chapter_8_summary(ch1_summary)
        # 聚合生成 附录
        combined_data["appendix"] = get_appendix_data(df_paper_final, df_long_final, df_horiz_final, target_years)

        return {"status": "success", "data": combined_data, "ch1_data": ch1_summary}
    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
