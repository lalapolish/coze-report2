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
        
        # 读取 Excel 第一个工作表
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
        df.columns = df.columns.str.strip()

        # 2. 基础数据清洗
        df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        target_years = [2020, 2021, 2022, 2023, 2024]

        # ==========================================
        # --- 第 2 章：发文规模 (Chapter 2) ---
        # ==========================================
        
        # 【表1：趋势数据逻辑 - table_1_trend】
        # 确保包含 2020-2024 所有年份，缺失补 0
        trend_series = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
        trend_df = trend_series.reindex(target_years, fill_value=0).reset_index()
        trend_df.columns = ['year', 'count'] # 统一使用英文 Key
        trend_data = trend_df.to_dict(orient='records')

        # 【表2：学院统计逻辑 - table_2_unit】
        unit_table = pd.pivot_table(
            df[df['发表年份'].isin(target_years)], 
            index='所属单位', 
            columns='发表年份', 
            aggfunc='size', 
            fill_value=0
        )
        
        # 补全年份列
        for y in target_years:
            if y not in unit_table.columns:
                unit_table[y] = 0
        
        # 计算总计并按降序排列
        unit_table['total'] = unit_table.sum(axis=1)
        unit_table = unit_table.sort_values(by='total', ascending=False).reset_index()

        # 过滤指定单位后缀
        valid_suffixes = ('学院', '学部', '图书馆', '研究院') 
        unit_table = unit_table[unit_table['所属单位'].astype(str).str.endswith(valid_suffixes, na=False)]
        
        # 插入序号 id
        unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
        
        # 重命名为扣子可识别的英文参数名
        column_mapping = {
            '所属单位': 'unit_name',
            2020: 'year_2020',
            2021: 'year_2021',
            2022: 'year_2022',
            2023: 'year_2023',
            2024: 'year_2024'
        }
        unit_table = unit_table.rename(columns=column_mapping)

        # 显式指定列顺序：序号 -> 单位 -> 各年份 -> 总计
        desired_order = ['id', 'unit_name', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']
        unit_table = unit_table[desired_order]
        unit_data = unit_table.to_dict(orient='records')

        # ==========================================
        # --- 其他未完成章节预留区 (待开发) ---
        # ==========================================
        # 预留章节 3：[待填入逻辑]
        # 预留章节 4：[待填入逻辑]
        # 预留章节 5：[待填入逻辑]


        # --- 最终结果构建 (确保表1在表2之前) ---
        return {
            "status": "success",
            "report_title": "山东师范大学人文社会科学科研成果发展态势分析报告（2020-2024）",
            "chapter_2": {
                "title": "发文规模趋势与构成分析",
                "table_1_trend": trend_data,  # 趋势表
                "table_2_unit": unit_data     # 学院表
            }
            # 后续在此添加 "chapter_3": {...}
        }

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        return {"status": "error", "message": str(e), "traceback": error_msg}

@app.get("/")
def home():
    return {"message": "论文分析 API 已就绪，第2章功能已锁定"}
