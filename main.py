from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import numpy as np
import io
import requests
import traceback

app = FastAPI(openapi_version="3.0.2")

class FileInput(BaseModel):
    file_url: str 

# =================================================================
# 0. 通用工具：日期解析与标准化
# =================================================================

def parse_year(df, date_col, year_col):
    if date_col in df.columns:
        return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
    if year_col in df.columns:
        return pd.to_numeric(df[year_col], errors='coerce')
    return None

def clean_unit_name(name):
    return str(name).split('（')[0].split('(')[0].strip()

def get_standard_2_items(df, year_col_name, target_years):
    """通用：返回 2 个指标 (1.趋势, 2.学院分布)"""
    temp = df.copy()
    temp['unit_clean'] = temp['所属单位'].apply(clean_unit_name)
    
    # 指标 1: 历年趋势
    trend = temp[temp[year_col_name].isin(target_years)].groupby(year_col_name).size().reindex(target_years, fill_value=0).reset_index(name='count')
    
    # 指标 2: 学院分布
    valid = temp[temp[year_col_name].isin(target_years)]
    unit_table = pd.pivot_table(valid, index='unit_clean', columns=year_col_name, aggfunc='size', fill_value=0)
    mapping = {y: f'year_{y}' for y in target_years}
    unit_table = unit_table.rename(columns=mapping).reset_index()
    unit_table = unit_table[unit_table['unit_clean'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    unit_table['total_count'] = unit_table[[f'year_{y}' for y in target_years]].sum(axis=1)
    
    return {
        "trend_list": trend.rename(columns={year_col_name: 'year'}).to_dict(orient='records'),
        "unit_list": unit_table.rename(columns={'unit_clean': 'unit_name'}).sort_values('total_count', ascending=False).to_dict(orient='records')
    }

# =================================================================
# 【第 2 章】科研论文规模 (2 个指标)
# =================================================================
def get_chapter_2(df, target_years):
    return get_standard_2_items(df, '发表年份', target_years)

# =================================================================
# 【第 3 章】高水平论文等级 (2 个指标)
# =================================================================
def get_chapter_3(df, target_years):
    temp = df.copy()
    temp['unit_clean'] = temp['所属单位'].apply(clean_unit_name)
    level_map = {'B级': 'level_B', 'C级': 'level_C', 'D级': 'level_D', 'E级': 'level_E', 'F级': 'level_F'}
    temp['rank_level'] = temp['学校认定等级'].apply(lambda x: next((v for k,v in level_map.items() if k[0] in str(x).upper()), "level_other"))
    
    v3 = temp[temp['发表年份'].isin(target_years)]
    # 指标 1: 历年各等级趋势
    chart = pd.pivot_table(v3, index='发表年份', columns='rank_level', aggfunc='size', fill_value=0)
    for lv in level_map.values(): 
        if lv not in chart.columns: chart[lv] = 0
    chart = chart[list(level_map.values())].reindex(target_years, fill_value=0).reset_index()
    
    # 指标 2: 各单位高水平排行
    unit_df = v3[v3['unit_clean'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    table = pd.pivot_table(unit_df, index='unit_clean', columns='rank_level', aggfunc='size', fill_value=0)
    for lv in level_map.values():
        if lv not in table.columns: table[lv] = 0
    table['total_count'] = table.sum(axis=1)
    
    return {
        "level_trend_chart": chart.rename(columns={'发表年份':'year'}).to_dict(orient='records'),
        "unit_rank_table": table.reset_index().rename(columns={'unit_clean':'unit_name'}).sort_values('total_count', ascending=False).to_dict(orient='records')
    }

# =================================================================
# 【第 4 章】科研项目规模 (13 个指标)
# =================================================================
def get_chapter_4(df_v, df_h, target_years):
    # 纵向数据处理
    df_v['year'] = parse_year(df_v, '立项日期', '立项年份')
    
    def get_sub_v(keyword):
        sub = df_v[df_v['项目级别'].str.contains(keyword, na=False)] if '项目级别' in df_v.columns else pd.DataFrame()
        return get_standard_2_items(sub, 'year', target_years) if not sub.empty else {"trend_list":[], "unit_list":[]}

    # 细分 13 个指标：
    # 1-2: 纵向总计 (2)
    v_total = get_standard_2_items(df_v, 'year', target_years)
    # 3-4: 国家社科 (2)
    v_nss = get_sub_v("国家社科")
    # 5-6: 国家自科 (2)
    v_nns = get_sub_v("国家自科")
    # 7-8: 教育部 (2)
    v_moe = get_sub_v("教育部")
    # 9-10: 省级 (2)
    v_prov = get_sub_v("省")
    # 11: 其他纵向趋势 (1)
    v_other_trend = v_total['trend_list'] # 简版
    
    # 12-13: 横向总计 (2)
    h_total = {"trend_list":[], "unit_list":[]}
    if not df_h.empty:
        df_h['year'] = parse_year(df_h, '立项日期', '立项年份')
        h_total = get_standard_2_items(df_h, 'year', target_years)

    return {
        "vertical_total": v_total,           # 2
        "national_social": v_nss,           # 2
        "national_natural": v_nns,          # 2
        "moe_project": v_moe,               # 2
        "provincial_project": v_prov,        # 2
        "other_vertical_trend": v_other_trend, # 1
        "horizontal_total": h_total          # 2 -> 共 13
    }

# =================================================================
# 【第 5 章】高产学者分析 (6 个指标)
# =================================================================
def get_chapter_5(df_p, df_v, df_h, target_years):
    # 论文端
    df_p['year'] = pd.to_numeric(df_p['发表年份'], errors='coerce')
    p_valid = df_p[df_p['year'].isin(target_years)].copy()
    level_map = {'B级': 'level_B', 'C级': 'level_C', 'D级': 'level_D'}
    p_valid['rank'] = p_valid['学校认定等级'].apply(lambda x: next((v for k,v in level_map.items() if k[0] in str(x).upper()), "other"))
    stats = pd.pivot_table(p_valid, index=['作者姓名', '所属单位'], columns='rank', aggfunc='size', fill_value=0).reset_index()
    for lv in level_map.values(): 
        if lv not in stats.columns: stats[lv] = 0
    stats['total_all'] = stats.sum(axis=1, numeric_only=True)
    stats = stats.rename(columns={'作者姓名':'author', '所属单位':'unit'})

    # 指标 1-4: 论文 4 表
    p1 = stats[stats['total_all'] >= 15].sort_values('total_all', ascending=False).to_dict(orient='records')
    p2 = stats[stats['level_B'] >= 4].sort_values('level_B', ascending=False).to_dict(orient='records')
    p3 = stats[stats['level_C'] >= 4].sort_values('level_C', ascending=False).to_dict(orient='records')
    p4 = stats[stats['level_D'] >= 4].sort_values('level_D', ascending=False).to_dict(orient='records')

    # 指标 5-6: 项目 2 表
    df_v['year'] = parse_year(df_v, '立项日期', '立项年份')
    v_stats = df_v[df_v['year'].isin(target_years)].groupby('负责人').size().reset_index(name='count')
    p5 = v_stats[v_stats['count'] >= 5].sort_values('count', ascending=False).to_dict(orient='records')
    
    p6 = []
    if not df_h.empty:
        df_h['year'] = parse_year(df_h, '立项日期', '立项年份')
        h_stats = df_h[df_h['year'].isin(target_years)].groupby('项目负责人').size().reset_index(name='count')
        p6 = h_stats[h_stats['count'] >= 5].sort_values('count', ascending=False).to_dict(orient='records')

    return {
        "paper_total_ge_15": p1, "paper_level_B_ge_4": p2, "paper_level_C_ge_4": p3, "paper_level_D_ge_4": p4,
        "vertical_proj_ge_5": p5, "horizontal_proj_ge_5": p6  # 共 6 个
    }

# =================================================================
# 【第 6/7 章】著作与获奖 (各 2 个指标)
# =================================================================
def get_chapter_6(df, target_years):
    df['year'] = parse_year(df, '出版时间', '发表年份')
    return get_standard_2_items(df, 'year', target_years)

def get_chapter_7(df, target_years):
    df['year'] = parse_year(df, '获奖日期', '发表年份')
    return get_standard_2_items(df, 'year', target_years)

# =================================================================
# 主接口
# =================================================================

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        res = requests.get(input.file_url)
        all_sheets = pd.read_excel(io.BytesIO(res.content), sheet_name=None)
        years = [2020, 2021, 2022, 2023, 2024]
        out = {}

        if "科研论文" in all_sheets:
            df_p = all_sheets["科研论文"]
            out["chapter_2"] = get_chapter_2(df_p, years)
            out["chapter_3"] = get_chapter_3(df_p, years)

        if "纵向项目" in all_sheets:
            df_v, df_h = all_sheets["纵向项目"], all_sheets.get("横向项目", pd.DataFrame())
            out["chapter_4"] = get_chapter_4(df_v, df_h, years)
            if "科研论文" in all_sheets:
                out["chapter_5"] = get_chapter_5(all_sheets["科研论文"], df_v, df_h, years)

        if "专著" in all_sheets:
            out["chapter_6"] = get_chapter_6(all_sheets["专著"], years)

        if "获奖" in all_sheets:
            out["chapter_7"] = get_chapter_7(all_sheets["获奖"], years)

        return {"status": "success", "data": out}
    except Exception as e:
        return {"status": "error", "message": str(e), "trace": traceback.format_exc()}
