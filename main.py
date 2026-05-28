from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import io
import requests

app = FastAPI(openapi_version="3.0.2")

class FileInput(BaseModel):
    file_url: str 

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        # 1. 下载并读取文件
        response = requests.get(input.file_url)
        response.raise_for_status()
        content = response.content
        
        # 读取第一个工作表
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
        df.columns = df.columns.str.strip()

        # 2. 基础数据清洗
        df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        target_years = [2020, 2021, 2022, 2023, 2024]

        # 【核心修正：强力清洗单位名称】
        def clean_unit_name(name):
            name = str(name)
            return name.split('（')[0].split('(')[0].strip()

        df['所属单位'] = df['所属单位'].apply(clean_unit_name)

        # ==========================================
        # --- 第 2 章：发文规模 (论文类) ---
        # ==========================================
        
        # 1. 趋势数据 (Chapter 2)
        trend_df_2 = df[df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index()
        trend_df_2.columns = ['year', 'count']
        trend_data_2 = trend_df_2.to_dict(orient='records')

        # 2. 学院统计 (Chapter 2)
        unit_table_2 = pd.pivot_table(
            df[df['发表年份'].isin(target_years)], 
            index='所属单位', 
            columns='发表年份', 
            aggfunc='size', 
            fill_value=0
        )
        for y in target_years:
            if y not in unit_table_2.columns: unit_table_2[y] = 0

        unit_table_2 = unit_table_2.reset_index()
        valid_pattern = '学院|学部|图书馆|研究院|中心'
        unit_table_2 = unit_table_2[unit_table_2['所属单位'].str.contains(valid_pattern, na=False)]
        unit_table_2 = unit_table_2[unit_table_2['所属单位'] != '继续教育与培训学部']
        
        unit_table_2['total'] = unit_table_2[target_years].sum(axis=1)
        unit_table_2 = unit_table_2.sort_values(by='total', ascending=False)
        unit_table_2.insert(0, 'id', range(1, len(unit_table_2) + 1))
        
        column_mapping = {'所属单位': 'unit_name', 2020: 'year_2020', 2021: 'year_2021', 2022: 'year_2022', 2023: 'year_2023', 2024: 'year_2024'}
        unit_table_2 = unit_table_2.rename(columns=column_mapping)
        desired_order = ['id', 'unit_name', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']
        unit_data_2 = unit_table_2[desired_order].to_dict(orient='records')

        # ==========================================
        # --- 第 6 章：专著出版规模 (Chapter 6) ---
        # ==========================================
        # 逻辑：与第 2 章一致，针对专著数据进行统计
        
        # 1. 专著年度趋势统计 (对应图1)
        trend_df_6 = df[df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index()
        trend_df_6.columns = ['year', 'count']
        trend_data_6 = trend_df_6.to_dict(orient='records')

        # 2. 各学院专著出版量统计 (对应表1)
        unit_table_6 = pd.pivot_table(
            df[df['发表年份'].isin(target_years)], 
            index='所属单位', 
            columns='发表年份', 
            aggfunc='size', 
            fill_value=0
        )
        for y in target_years:
            if y not in unit_table_6.columns: unit_table_6[y] = 0

        unit_table_6 = unit_table_6.reset_index()
        # 保持同样的学院筛选逻辑
        unit_table_6 = unit_table_6[unit_table_6['所属单位'].str.contains(valid_pattern, na=False)]
        unit_table_6 = unit_table_6[unit_table_6['所属单位'] != '继续教育与培训学部']
        
        unit_table_6['total'] = unit_table_6[target_years].sum(axis=1)
        unit_table_6 = unit_table_6.sort_values(by='total', ascending=False)
        unit_table_6.insert(0, 'id', range(1, len(unit_table_6) + 1))
        
        # 重命名与第 2 章保持一致
        unit_table_6 = unit_table_6.rename(columns=column_mapping)
        unit_data_6 = unit_table_6[desired_order].to_dict(orient='records')


        # --- 最终返回 ---
        return {
            "status": "success",
            "report_title": "山东师范大学人文社会科学科研成果发展态势分析报告（2020-2024）",
            "chapter_2": {
                "title": "发文规模趋势与构成分析",
                "table_1_trend": trend_data_2,
                "table_2_unit": unit_data_2
            },
            "chapter_6": {
                "title": "著作出版规模与构成分析",
                "table_1_trend": trend_data_6, # 对应图1：年度变化
                "table_2_unit": unit_data_6     # 对应表1：各学院年度变化
            }
        }

    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

@app.get("/")
def home():
    return {"message": "API 已更新：增加了第 6 章专著分析模块"}
