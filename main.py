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
        # 1. 下载文件
        response = requests.get(input.file_url)
        response.raise_for_status()
        content = response.content
        
        # 2. 读取 Excel
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
        df.columns = df.columns.str.strip() # 清理列名空格

        # 3. 统一转换发表年份为数字，非数字转为 NaN
        df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        
        # 定义我们需要统计的标准年份区间
        target_years = [2020, 2021, 2022, 2023, 2024]

        # --- 第2章：发文规模逻辑 ---
        
        # 1. 趋势数据 (对应图：发文量变化)
        # 统计每一年的数量，并强制包含 2020-2024，缺失年份补 0
        trend_series = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
        trend_df = trend_series.reindex(target_years, fill_value=0).reset_index()
        trend_df.columns = ['发表年份', '论文数量'] # 修改表头为“论文数量”
        trend_data = trend_df.to_dict(orient='records')

        # 2. 学院统计 (对应表：各学院发文量统计)
        # 透视表逻辑
        unit_table = pd.pivot_table(
            df[df['发表年份'].isin(target_years)], 
            index='所属单位', 
            columns='发表年份', 
            aggfunc='size', 
            fill_value=0
        )
        
        # 确保透视表里也包含所有目标年份列，哪怕全是0
        for y in target_years:
            if y not in unit_table.columns:
                unit_table[y] = 0
        
        # 只保留 2020-2024 这几列，防止多出其他年份
        unit_table = unit_table[target_years]

        # 计算总计
        unit_table['总计'] = unit_table.sum(axis=1)
        unit_table = unit_table.sort_values(by='总计', ascending=False).reset_index()

        # 学院过滤逻辑：根据你提供的特定单位后缀/全称过滤
        # 为了兼容性，建议使用具体的后缀识别
        valid_suffixes = ('学院', '学部', '图书馆', '研究院') 
        unit_table = unit_table[unit_table['所属单位'].astype(str).str.endswith(valid_suffixes, na=False)]
        
        # 插入序号列
        unit_table.insert(0, '序号', range(1, len(unit_table) + 1))
        
        # 格式化列名，如 2020 -> "2020年"
        new_columns = []
        for col in unit_table.columns:
            if col in target_years:
                new_columns.append(f"{col}年")
            else:
                new_columns.append(str(col))
        unit_table.columns = new_columns

        # 转换成字典格式供 API 返回
        unit_data = unit_table.to_dict(orient='records')

        # --- 返回结果结构 ---
        return {
            "status": "success",
            "report_title": "山东师范大学人文社会科学科研成果发展态势分析报告（2020-2024）",
            "chapter_2": {
                "title": "发文规模",
                "chart_trend": trend_data,  # 这里面现在是 '发表年份' 和 '论文数量'，且年份完整
                "table_unit": unit_data     # 这里面是序号、所属单位、2020年...总计
            }
        }

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        return {"status": "error", "message": str(e), "traceback": error_msg}

@app.get("/")
def home():
    return {"message": "论文分析 API 已就绪"}
