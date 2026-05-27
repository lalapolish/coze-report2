from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import io
import requests
from collections import OrderedDict # 导入有序字典

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

        # ==========================================
        # --- 第 2 章：发文规模 (Chapter 2) ---
        # ==========================================
        
        # 【表1：趋势数据逻辑 - table_1_trend】
        trend_series = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
        trend_df = trend_series.reindex(target_years, fill_value=0).reset_index()
        trend_df.columns = ['year', 'count']
        
        # 使用 OrderedDict 确保趋势图数据顺序
        trend_data = []
        for _, row in trend_df.iterrows():
            item = OrderedDict()
            item["year"] = int(row["year"])
            item["count"] = int(row["count"])
            trend_data.append(item)

        # 【表2：学院统计逻辑 - table_2_unit】
        # 先按年份透视
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

        # 重置索引，准备进行复杂的字符串筛选
        unit_table = unit_table.reset_index()

        # --- 关键筛选逻辑逻辑修改 ---
        # 1. 包含核心关键词（学院、学部、图书馆、研究院），解决带括号别名的问题
        valid_pattern = '学院|学部|图书馆|研究院'
        unit_table = unit_table[unit_table['所属单位'].str.contains(valid_pattern, na=False)]
        
        # 2. 排除特定的非学术/培训单位
        exclude_units = ['继续教育与培训学部']
        unit_table = unit_table[~unit_table['所属单位'].isin(exclude_units)]
        # --- 筛选逻辑结束 ---

        # 计算总计并降序排列
        unit_table['total'] = unit_table[target_years].sum(axis=1)
        unit_table = unit_table.sort_values(by='total', ascending=False)
        
        # 重新生成序号 id
        unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
        
        # 3. 构造强制有序的列表数据
        unit_data = []
        for _, row in unit_table.iterrows():
            # 使用 OrderedDict 显式锁定列顺序
            row_dict = OrderedDict()
            row_dict["id"] = int(row["id"])
            row_dict["unit_name"] = str(row["所属单位"])
            row_dict["year_2020"] = int(row[2020])
            row_dict["year_2021"] = int(row[2021])
            row_dict["year_2022"] = int(row[2022])
            row_dict["year_2023"] = int(row[2023])
            row_dict["year_2024"] = int(row[2024])
            row_dict["total"] = int(row["total"])
            unit_data.append(row_dict)

        # ==========================================
        # --- 其他未完成章节预留区 (待开发) ---
        # ==========================================
        # 预留章节 3：[待填入逻辑]


        # --- 最终结果构建 ---
        # 使用 OrderedDict 确保 chapter 内部 table_1 在 table_2 之前
        chapter_2_content = OrderedDict()
        chapter_2_content["title"] = "发文规模趋势与构成分析"
        chapter_2_content["table_1_trend"] = trend_data
        chapter_2_content["table_2_unit"] = unit_data

        return OrderedDict([
            ("status", "success"),
            ("report_title", "山东师范大学人文社会科学科研成果发展态势分析报告（2020-2024）"),
            ("chapter_2", chapter_2_content)
        ])

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        return {"status": "error", "message": str(e), "traceback": error_msg}

@app.get("/")
def home():
    return {"message": "论文分析 API 已就绪，已优化单位筛选逻辑及排序"}
