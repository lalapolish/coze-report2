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
        
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
        df.columns = df.columns.str.strip()

        # 2. 基础数据清洗
        df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        target_years = [2020, 2021, 2022, 2023, 2024]

        # 【重点：清洗单位名称，合并别名】
        # 将中文括号和英文括号及内部内容全部删除，例如 "学院(研究所)" -> "学院"
        df['所属单位'] = df['所属单位'].astype(str).str.replace(r'[\(（].*?[\)）]', '', regex=True).str.strip()

        # ==========================================
        # --- 第 2 章：发文规模 (Chapter 2) ---
        # ==========================================
        
        # 1. 趋势数据 (table_1_trend)
        trend_df = df[df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index()
        trend_df.columns = ['year', 'count']
        trend_data = trend_df.to_dict(orient='records')

        # 2. 学院统计 (table_2_unit)
        # 因为前面已经清洗了名称，这里的 pivot 会自动将同名学院的量加在一起
        unit_table = pd.pivot_table(
            df[df['发表年份'].isin(target_years)], 
            index='所属单位', 
            columns='发表年份', 
            aggfunc='size', 
            fill_value=0
        )
        
        # 补全可能缺失的年份列
        for y in target_years:
            if y not in unit_table.columns:
                unit_table[y] = 0

        # 重置索引进行筛选
        unit_table = unit_table.reset_index()

        # 筛选核心单位并排除干扰项
        valid_pattern = '学院|学部|图书馆|研究院'
        unit_table = unit_table[unit_table['所属单位'].str.contains(valid_pattern, na=False)]
        unit_table = unit_table[unit_table['所属单位'] != '继续教育与培训学部']

        # 计算总计并排序
        unit_table['total'] = unit_table[target_years].sum(axis=1)
        unit_table = unit_table.sort_values(by='total', ascending=False)
        
        # 插入序号
        unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
        
        # 重命名为英文 Key (对应扣子配置)
        column_mapping = {
            '所属单位': 'unit_name',
            2020: 'year_2020',
            2021: 'year_2021',
            2022: 'year_2022',
            2023: 'year_2023',
            2024: 'year_2024'
        }
        unit_table = unit_table.rename(columns=column_mapping)

        # 锁定列顺序
        desired_order = ['id', 'unit_name', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']
        unit_table = unit_table[desired_order]
        
        unit_data = unit_table.to_dict(orient='records')

        # ==========================================
        # --- 其他未完成章节预留区 (待开发) ---
        # ==========================================
        # 预留章节 3：[待填入逻辑]


        # --- 最终返回 ---
        return {
            "status": "success",
            "report_title": "山东师范大学人文社会科学科研成果发展态势分析报告（2020-2024）",
            "chapter_2": {
                "title": "发文规模趋势与构成分析",
                "table_1_trend": trend_data,
                "table_2_unit": unit_data
            }
        }

    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

@app.get("/")
def home():
    return {"message": "论文分析 API 已就绪，已合并同名学院并去除别名"}
