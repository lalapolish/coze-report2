from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
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
    trend = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    valid_df = df[df['发表年份'].isin(target_years)]
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
        "table_1_trend": trend.to_dict(orient='records'),
        "table_2_unit": unit_table[['id', 'unit_name', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']].to_dict(orient='records')
    }

# ----------------- 【第 3 章：发文期刊】 -----------------
def get_chapter_3_data(df, target_years):
    # TODO: 待补充作图逻辑
    return {"message": "第 3 章逻辑待开发"}

# ----------------- 【第 4 章：基金课题】 -----------------
def get_chapter_4_data(df, target_years):
    # TODO: 待补充作图逻辑
    return {"message": "第 4 章逻辑待开发"}

# ----------------- 【第 5 章：重要学者】 -----------------
def get_chapter_5_data(df, target_years):
    # TODO: 待补充多表综合逻辑
    return {"message": "第 5 章逻辑待开发"}

# ----------------- 【第 6 章：专著】 -----------------
def get_chapter_6_data(df, target_years):
    trend = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    unit_table = pd.pivot_table(df[df['发表年份'].isin(target_years)], index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
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
        "table_1_trend": trend.to_dict(orient='records'),
        "table_2_unit": unit_table[['id', 'unit_name', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']].to_dict(orient='records')
    }

# ----------------- 【第 7 章：获奖情况】 -----------------
# 依赖：获奖.xlsx
def get_chapter_7_data(df, target_years):
    # 1. 图 1：获奖数量变化趋势
    trend = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    # 2. 图 2：各等级获奖分布
    # 过滤目标年份数据
    valid_df = df[df['发表年份'].isin(target_years)].copy()
    
    # 清洗等级列名（防止有空格）
    valid_df['学校认定等级'] = valid_df['学校认定等级'].astype(str).str.strip()
    
    # 透视表：行是年份，列是等级
    dist_table = pd.pivot_table(
        valid_df, 
        index='发表年份', 
        columns='学校认定等级', 
        aggfunc='size', 
        fill_value=0
    )
    
    # 确保 A-F 级列都存在
    levels = ['A', 'B', 'C', 'D', 'E', 'F']
    for lv in levels:
        if lv not in dist_table.columns:
            dist_table[lv] = 0
            
    # 确保 2020-2024 年行都存在
    dist_table = dist_table.reindex(target_years, fill_value=0)
    
    # 重构表格格式
    dist_table = dist_table.reset_index()
    dist_table.columns.name = None # 移除交叉表留下的索引名
    
    # 按照要求的列名返回
    mapping = {
        '发表年份': 'year',
        'A': 'level_A', 'B': 'level_B', 'C': 'level_C',
        'D': 'level_D', 'E': 'level_E', 'F': 'level_F'
    }
    dist_table = dist_table.rename(columns=mapping)
    
    return {
        "table_1_trend": trend.to_dict(orient='records'),
        "table_2_level_dist": dist_table[['year', 'level_A', 'level_B', 'level_C', 'level_D', 'level_E', 'level_F']].to_dict(orient='records')
    }


# =================================================================
# 主接口：负责文件识别与任务分拣
# =================================================================

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        file_name = unquote(input.file_url.split('/')[-1])
        response = requests.get(input.file_url)
        df = pd.read_excel(io.BytesIO(response.content), sheet_name=0)
        df.columns = df.columns.str.strip()

        # 3. 预处理：统一“发表年份”列
        if '获奖日期' in df.columns: # 针对获奖表
            df['发表年份'] = pd.to_datetime(df['获奖日期'], errors='coerce').dt.year
        elif '出版时间' in df.columns: # 针对专著表
            df['发表年份'] = pd.to_datetime(df['出版时间'], errors='coerce').dt.year
        elif '发表年份' in df.columns:
            df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        elif '批准年份' in df.columns:
            df['发表年份'] = pd.to_numeric(df['批准年份'], errors='coerce')
        elif '获奖年份' in df.columns:
            df['发表年份'] = pd.to_numeric(df['获奖年份'], errors='coerce')

        # 4. 预处理：单位清洗
        if '所属单位' in df.columns:
            df['所属单位'] = df['所属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())

        target_years = [2020, 2021, 2022, 2023, 2024]
        result_data = {}

        # ----------------- 分路识别 -----------------
        if "论文" in file_name:
            result_data["chapter_2"] = get_chapter_2_data(df, target_years)
            result_data["chapter_3"] = get_chapter_3_data(df, target_years)

        elif "项目" in file_name or "课题" in file_name:
            result_data["chapter_4"] = get_chapter_4_data(df, target_years)

        elif "专著" in file_name:
            result_data["chapter_6"] = get_chapter_6_data(df, target_years)

        elif "获奖" in file_name:
            # 执行第 7 章逻辑
            result_data["chapter_7"] = get_chapter_7_data(df, target_years)

        else:
            return {"status": "warning", "message": f"文件名 [{file_name}] 未匹配到已知业务表"}

        return {
            "status": "success",
            "detected_file": file_name,
            "data": result_data
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
