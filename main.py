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
# 工具函数：处理日期和清洗单位
# =================================================================

def parse_year(df, date_col, year_col):
    """兼容处理：优先从日期列提取年份，若无则取年份列"""
    if date_col in df.columns:
        # 处理类似 2021.10.01 的格式
        return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
    if year_col in df.columns:
        return pd.to_numeric(df[year_col], errors='coerce')
    return None

def clean_unit_name(name):
    """清洗单位名称：去除括号，只保留核心学院名"""
    return str(name).split('（')[0].split('(')[0].strip()

# =================================================================
# 【第 2 章】科研论文规模分析逻辑
# =================================================================

def get_chapter_2_data(df, target_years):
    temp_df = df.copy()
    temp_df['unit_name_clean'] = temp_df['所属单位'].apply(clean_unit_name)
    
    # 趋势表
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index(name='count')
    
    # 单位分布表
    valid_df = temp_df[temp_df['发表年份'].isin(target_years)]
    unit_table = pd.pivot_table(valid_df, index='unit_name_clean', columns='发表年份', aggfunc='size', fill_value=0)
    
    # 强制生成 key 名为 year_202x 的列
    mapping = {y: f'year_{y}' for y in target_years}
    unit_table = unit_table.rename(columns=mapping).reset_index()
    
    # 只保留主要教学科研单位
    unit_table = unit_table[unit_table['unit_name_clean'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    unit_table['total_count'] = unit_table[[f'year_{y}' for y in target_years]].sum(axis=1)
    unit_table = unit_table.sort_values(by='total_count', ascending=False)
    
    return {
        "trend_list": trend.rename(columns={'发表年份':'year'}).to_dict(orient='records'), 
        "unit_list": unit_table.rename(columns={'unit_name_clean':'unit_name'}).to_dict(orient='records')
    }

# =================================================================
# 【第 3 章】高水平论文（期刊）分析逻辑
# =================================================================

def get_chapter_3_data(df, target_years):
    temp_df = df.copy()
    temp_df['unit_name_clean'] = temp_df['所属单位'].apply(clean_unit_name)
    
    # 内部等级映射（中文转英文 Key）
    level_map = {'B级': 'level_B', 'C级': 'level_C', 'D级': 'level_D', 'E级': 'level_E', 'F级': 'level_F'}
    
    def map_level(x):
        x = str(x).upper()
        for cn, en in level_map.items():
            if cn[0] in x: return en
        return "level_other"

    df_v3 = temp_df[temp_df['发表年份'].isin(target_years)].copy()
    df_v3['rank_level'] = df_v3['学校认定等级'].apply(map_level)
    
    # 1. 历年等级分布趋势
    chart = pd.pivot_table(df_v3, index='发表年份', columns='rank_level', aggfunc='size', fill_value=0)
    for lv in level_map.values():
        if lv not in chart.columns: chart[lv] = 0
    chart = chart[list(level_map.values())].reindex(target_years, fill_value=0).reset_index()
    
    # 2. 各单位高水平论文排行
    unit_df = df_v3[df_v3['unit_name_clean'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    table = pd.pivot_table(unit_df, index='unit_name_clean', columns='rank_level', aggfunc='size', fill_value=0)
    for lv in level_map.values():
        if lv not in table.columns: table[lv] = 0
    table['total_count'] = table.sum(axis=1)
    table = table.sort_values('total_count', ascending=False).reset_index()
    
    return {
        "year_level_chart": chart.rename(columns={'发表年份':'year'}).to_dict(orient='records'), 
        "unit_level_table": table.rename(columns={'unit_name_clean':'unit_name'}).head(10).to_dict(orient='records')
    }

# =================================================================
# 【第 4 章】科研项目（纵向/横向）分析逻辑
# =================================================================

def get_chapter_4_data(df_long, df_horiz, target_years):
    # 纵向项目趋势
    df_long['year'] = parse_year(df_long, '立项日期', '立项年份')
    long_trend = df_long[df_long['year'].isin(target_years)].groupby('year').size().reindex(target_years, fill_value=0).reset_index(name='count')
    
    # 横向项目趋势
    horiz_res = []
    if not df_horiz.empty:
        df_horiz['year'] = parse_year(df_horiz, '立项日期', '立项年份')
        h_trend = df_horiz[df_horiz['year'].isin(target_years)].groupby('year').size().reindex(target_years, fill_value=0).reset_index(name='count')
        horiz_res = h_trend.to_dict(orient='records')

    return {
        "longitudinal_trend": long_trend.to_dict(orient='records'), 
        "horizontal_trend": horiz_res
    }

# =================================================================
# 【第 5 章】高产学者分析逻辑 (论文+项目)
# =================================================================

def get_chapter_5_data(df_paper, df_long, df_horiz, target_years):
    # 1. 论文部分
    df_p = df_paper[df_paper['发表年份'].isin(target_years)].copy()
    level_map = {'B级': 'level_B', 'C级': 'level_C', 'D级': 'level_D', 'E级': 'level_E', 'F级': 'level_F'}
    df_p['rank_level'] = df_p['学校认定等级'].apply(lambda x: next((v for k,v in level_map.items() if k[0] in str(x).upper()), "level_other"))
    
    p_stats = pd.pivot_table(df_p, index=['作者姓名', '所属单位'], columns='rank_level', aggfunc='size', fill_value=0)
    for lv in level_map.values():
        if lv not in p_stats.columns: p_stats[lv] = 0
    p_stats['total_count'] = p_stats.sum(axis=1)
    p_stats = p_stats.reset_index().rename(columns={'作者姓名':'author_name', '所属单位':'unit_name'})
    
    paper_out = {
        "top_total_ge_15": p_stats[p_stats['total_count'] >= 15].sort_values('total_count', ascending=False).to_dict(orient='records'),
        "top_B_level_ge_4": p_stats[p_stats['level_B'] >= 4].sort_values('level_B', ascending=False).to_dict(orient='records'),
        "top_C_level_ge_4": p_stats[p_stats['level_C'] >= 4].sort_values('level_C', ascending=False).to_dict(orient='records')
    }

    # 2. 项目部分
    df_long['year'] = parse_year(df_long, '立项日期', '立项年份')
    v_stats = df_long[df_long['year'].isin(target_years)].groupby('负责人').size().reset_index(name='project_count')
    
    h_out = []
    if not df_horiz.empty:
        df_horiz['year'] = parse_year(df_horiz, '立项日期', '立项年份')
        h_stats = df_horiz[df_horiz['year'].isin(target_years)].groupby('项目负责人').size().reset_index(name='project_count')
        h_out = h_stats[h_stats['project_count'] >= 5].rename(columns={'项目负责人':'author_name'}).to_dict(orient='records')

    project_out = {
        "vertical_top": v_stats[v_stats['project_count'] >= 5].rename(columns={'负责人':'author_name'}).to_dict(orient='records'),
        "horizontal_top": h_out
    }

    return {"scholar_papers": paper_out, "scholar_projects": project_out}

# =================================================================
# 【第 6 & 7 章】专著与获奖简要趋势
# =================================================================

def get_simple_trend(df, time_col, target_years):
    df['year'] = pd.to_datetime(df[time_col], errors='coerce').dt.year
    trend = df[df['year'].isin(target_years)].groupby('year').size().reindex(target_years, fill_value=0).reset_index(name='count')
    return trend.to_dict(orient='records')

# =================================================================
# 主接口：读取数据并按章节顺序组装 JSON
# =================================================================

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        # 下载并读取 Excel
        response = requests.get(input.file_url)
        all_sheets = pd.read_excel(io.BytesIO(response.content), sheet_name=None)
        
        target_years = [2020, 2021, 2022, 2023, 2024]
        
        # 准备一个临时存储字典
        results = {}

        # 逻辑处理：根据 Sheet 是否存在按需计算
        if "科研论文" in all_sheets:
            df_p = all_sheets["科研论文"]
            df_p['发表年份'] = pd.to_numeric(df_p['发表年份'], errors='coerce')
            results["c2"] = get_chapter_2_data(df_p, target_years)
            results["c3"] = get_chapter_3_data(df_p, target_years)
            # C5 依赖论文和项目，稍后处理

        if "纵向项目" in all_sheets:
            df_long = all_sheets["纵向项目"]
            df_horiz = all_sheets.get("横向项目", pd.DataFrame())
            results["c4"] = get_chapter_4_data(df_long, df_horiz, target_years)
            
            # 处理第 5 章
            if "科研论文" in all_sheets:
                results["c5"] = get_chapter_5_data(all_sheets["科研论文"], df_long, df_horiz, target_years)

        if "专著" in all_sheets:
            results["c6"] = get_simple_trend(all_sheets["专著"], '出版时间', target_years)

        if "获奖" in all_sheets:
            results["c7"] = get_simple_trend(all_sheets["获奖"], '获奖日期', target_years)

        # --- 核心：严格按章节顺序组装最终输出 ---
        final_ordered_data = {}
        if "c2" in results: final_ordered_data["chapter_2_scale"] = results["c2"]
        if "c3" in results: final_ordered_data["chapter_3_journals"] = results["c3"]
        if "c4" in results: final_ordered_data["chapter_4_projects"] = results["c4"]
        if "c5" in results: final_ordered_data["chapter_5_scholars"] = results["c5"]
        if "c6" in results: final_ordered_data["chapter_6_monographs"] = {"trend": results["c6"]}
        if "c7" in results: final_ordered_data["chapter_7_awards"] = {"trend": results["c7"]}

        return {
            "status": "success",
            "data": final_ordered_data
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }
