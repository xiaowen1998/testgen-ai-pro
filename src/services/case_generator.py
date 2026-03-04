"""
用例生成服务
双阶段生成：测试点分析 -> 用例生成
"""


import re
import difflib
import time
from typing import List, Tuple, Optional, Dict, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st

from src.models import TestCase, TestPoint, Priority
from src.services.ai_service import AIService, AIServiceError
from src.config import (
    STAGE2_MAX_POINTS_PER_BATCH,
    PRIORITY_ORDER,
    get_qwen_model_list,
)


class CaseGeneratorError(Exception):
    """用例生成异常"""
    pass


class GenerationResult:
    """生成结果封装"""
    def __init__(self):
        self.cases: List[TestCase] = []
        self.test_points: List[TestPoint] = []
        self.coverage_map: Dict[int, bool] = {}
        self.elapsed_stage1: float = 0.0
        self.elapsed_stage2: float = 0.0
        self.is_valid: bool = True
        self.error_message: str = ""


class CaseGenerator:
    """用例生成器"""
    
    def __init__(self, ai_service: Optional[AIService] = None, input_source: str = "text"):
        self.ai = ai_service or AIService()
        self.input_source = input_source
        self.similarity_threshold = 0.92  # 去重相似度阈值
    
    def _get_stage1_model(self) -> Optional[str]:
        """获取阶段1使用的模型"""
        model_list = get_qwen_model_list()
        return model_list[0] if model_list else "qwen-turbo"
    
    def _get_stage2_model(self) -> Optional[str]:
        """获取阶段2使用的模型"""
        model_list = get_qwen_model_list()
        return model_list[0] if model_list else "qwen-turbo"
    
    def generate(self, content: str, progress_callback: Optional[Callable] = None) -> GenerationResult:
        """
        完整生成流程：分析测试点 -> 生成用例 -> 补全缺失 -> 严格校验
        
        Args:
            content: 需求内容
            progress_callback: 进度回调函数 (message: str)
        
        Returns:
            GenerationResult: 生成结果
        """
        result = GenerationResult()
        start_total = time.time()
        
        # 阶段1：分析测试点
        stage1_start = time.time()
        if progress_callback:
            progress_callback("📝 第1阶段：分析需求，识别测试点...")
        
        test_points = self.analyze_points(content)
        result.test_points = test_points
        result.elapsed_stage1 = time.time() - stage1_start
        
        if not test_points:
            result.is_valid = False
            result.error_message = "未识别到测试点，请检查需求描述或重试。"
            return result
        
        if progress_callback:
            progress_callback(f"✅ 识别到 {len(test_points)} 个测试点")
        
        # 阶段2：生成用例
        stage2_start = time.time()
        if progress_callback:
            progress_callback(f"🎯 第2阶段：基于 {len(test_points)} 个测试点生成用例...")
        
        cases = self.generate_cases(test_points, progress_callback)
        result.cases = cases
        result.coverage_map = self._track_coverage(cases, test_points)
        result.elapsed_stage2 = time.time() - stage2_start
        
        # 检查缺失的测试点并补全
        missing_count = sum(1 for i in range(len(test_points)) if not result.coverage_map.get(i, False))
        if missing_count > 0 and progress_callback:
            progress_callback(f"🔄 检测到 {missing_count} 个测试点未覆盖，正在精准补全…")
            cases = self.fill_missing_cases(test_points, cases)
            result.cases = cases
            result.coverage_map = self._track_coverage(cases, test_points)
        
        # 严格校验
        is_valid, error_msg = self.strict_validate_cases(cases, test_points)
        result.is_valid = is_valid
        result.error_message = error_msg
        
        # 重新编号
        for i, case in enumerate(cases, 1):
            case.case_id = f"TC{i:03d}"
        
        return result
    
    def analyze_points(self, content: str) -> List[TestPoint]:
        """
        阶段1：分析需求，识别测试点
        """
        if not self.ai.is_configured():
            raise CaseGeneratorError("未配置 QWEN_API_KEY")
        
        try:
            model = self._get_stage1_model()
            response = self.ai.analyze_test_points(content, model_override=model)
        except AIServiceError as e:
            raise CaseGeneratorError(f"AI服务错误: {e}")
        
        # 解析测试点
        points = []
        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue
            
            # 匹配 "测试点1：xxx"
            m = re.match(r"测试点\s*(\d+)\s*[：:]\s*(.+)", line, re.I)
            if m:
                num = int(m.group(1))
                desc = m.group(2).strip()
                points.append(TestPoint(id=num, title=desc))
                continue
            
            # 匹配 "1. xxx"
            m = re.match(r"(\d+)[\.．、]\s*(.+)", line)
            if m:
                num = int(m.group(1))
                desc = m.group(2).strip()
                points.append(TestPoint(id=num, title=desc))
        
        # 去重并排序
        seen = set()
        unique_points = []
        for p in points:
            if p.title not in seen:
                seen.add(p.title)
                unique_points.append(p)
        
        return sorted(unique_points, key=lambda x: x.id)
    
    def generate_cases(
        self,
        test_points: List[TestPoint],
        progress_callback: Optional[Callable] = None
    ) -> List[TestCase]:
        """
        阶段2：生成用例
        """
        if not test_points:
            return []
        
        # 分批处理
        batches = self._create_batches(test_points)
        
        if len(batches) == 1:
            # 单批，直接生成
            cases = self._generate_batch(batches[0])
        else:
            # 多批，并发生成
            cases = self._generate_batches_concurrent(batches, progress_callback)
        
        # 后处理（去重、排序，但不编号）
        cases = self._post_process(cases, test_points)
        
        return cases
    
    def _create_batches(self, test_points: List[TestPoint]) -> List[List[TestPoint]]:
        """创建批次"""
        if len(test_points) <= STAGE2_MAX_POINTS_PER_BATCH:
            return [test_points]
        
        return [
            test_points[i:i + STAGE2_MAX_POINTS_PER_BATCH]
            for i in range(0, len(test_points), STAGE2_MAX_POINTS_PER_BATCH)
        ]
    
    def _generate_batch(self, points: List[TestPoint]) -> List[TestCase]:
        """生成单批用例"""
        point_titles = [p.title for p in points]
        
        try:
            model = self._get_stage2_model()
            raw_cases = self.ai.generate_cases_for_batch(point_titles, model_override=model)
        except AIServiceError as e:
            raise CaseGeneratorError(f"AI生成失败: {e}")
        
        cases = []
        for data in raw_cases:
            tp_str = data.get("test_point", "")
            m = re.search(r"测试点\s*(\d+)", tp_str)
            if m:
                point_id = int(m.group(1))
            else:
                point_id = points[0].id
            
            try:
                case = TestCase.from_llm_response(data, point_id)
                cases.append(case)
            except Exception:
                continue
        
        return cases
    
    def _generate_batches_concurrent(
        self,
        batches: List[List[TestPoint]],
        progress_callback: Optional[Callable] = None
    ) -> List[TestCase]:
        """并发生成多批用例"""
        model_list = get_qwen_model_list()
        max_workers = min(len(batches), 3)
        
        results = {}
        completed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    self._generate_batch_with_model,
                    batch,
                    model_list[i % len(model_list)]
                ): i
                for i, batch in enumerate(batches)
            }
            
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception:
                    results[idx] = []
                
                completed += 1
                if progress_callback:
                    progress_callback(f"已完成 {completed}/{len(batches)} 批")
        
        # 合并结果
        all_cases = []
        for i in range(len(batches)):
            all_cases.extend(results.get(i, []))
        
        return all_cases
    
    def _generate_batch_with_model(
        self,
        points: List[TestPoint],
        model: str
    ) -> List[TestCase]:
        """使用指定模型生成一批用例"""
        point_titles = [p.title for p in points]
        
        try:
            raw_cases = self.ai.generate_cases_for_batch(point_titles, model)
        except Exception:
            return []
        
        cases = []
        for data in raw_cases:
            tp_str = data.get("test_point", "")
            m = re.search(r"测试点\s*(\d+)", tp_str)
            point_id = int(m.group(1)) if m else points[0].id
            
            try:
                case = TestCase.from_llm_response(data, point_id)
                cases.append(case)
            except Exception:
                continue
        
        return cases
    
    def _track_coverage(self, cases: List[TestCase], test_points: List[TestPoint]) -> Dict[int, bool]:
        """统计每个测试点是否至少被 1 条用例覆盖"""
        coverage: Dict[int, bool] = {i: False for i in range(len(test_points))}
        for c in cases:
            tp_id = c.test_point_id
            idx = tp_id - 1  # 测试点ID从1开始
            if 0 <= idx < len(test_points):
                coverage[idx] = True
        return coverage
    
    def strict_validate_cases(self, cases: List[TestCase], test_points: List[TestPoint]) -> Tuple[bool, str]:
        """
        严格校验：用例数必须 ≥ 测试点数，且每个测试点至少被覆盖 1 次
        
        Returns:
            (是否通过, 错误信息)
        """
        case_count = len(cases)
        point_count = len(test_points)
        
        if case_count < point_count:
            missing = point_count - case_count
            return False, f"用例数量({case_count}) < 测试点数量({point_count})，少了 {missing} 条。"
        
        # 检查每个测试点是否被覆盖
        coverage = self._track_coverage(cases, test_points)
        uncovered = [i + 1 for i in range(len(test_points)) if not coverage.get(i, False)]
        
        if uncovered:
            return False, f"测试点 {uncovered} 没有用例覆盖。"
        
        return True, ""
    
    def fill_missing_cases(
        self,
        test_points: List[TestPoint],
        cases: List[TestCase]
    ) -> List[TestCase]:
        """为未覆盖的测试点单独补全"""
        covered = {c.test_point_id for c in cases if not c.is_placeholder}
        missing = [p for p in test_points if p.id not in covered]
        
        if not missing:
            return cases
        
        for point in missing:
            # 尝试单独生成
            new_cases = self._try_generate_for_point(point)
            if new_cases:
                cases.append(new_cases[0])
            else:
                # 创建占位用例
                cases.append(self._create_placeholder(point))
        
        return cases
    
    def _try_generate_for_point(self, point: TestPoint) -> List[TestCase]:
        """尝试为单个测试点生成用例"""
        for attempt in range(3):  # 最多重试3次
            try:
                raw_cases = self.ai.generate_cases_for_batch([point.title], self._get_stage2_model())
                if raw_cases:
                    cases = []
                    for data in raw_cases:
                        data["test_point"] = f"测试点{point.id}"
                        try:
                            case = TestCase.from_llm_response(data, point.id)
                            cases.append(case)
                        except Exception:
                            continue
                    return cases
            except Exception:
                time.sleep(1)
        return []
    
    def _post_process(
        self,
        cases: List[TestCase],
        test_points: List[TestPoint]
    ) -> List[TestCase]:
        """后处理：去重、排序"""
        # 按测试点分组去重
        cases = self._dedupe_by_test_point(cases, test_points)
        
        # 按优先级排序
        cases = sorted(cases, key=lambda c: PRIORITY_ORDER.get(c.priority.value, 1))
        
        # 补充缺失的测试点
        cases = self._fill_missing_points(cases, test_points)
        
        return cases
    
    def _dedupe_by_test_point(
        self,
        cases: List[TestCase],
        test_points: List[TestPoint]
    ) -> List[TestCase]:
        """按测试点分组去重，确保每个测试点至少保留1条"""
        groups: dict[int, List[TestCase]] = {}
        for c in cases:
            pid = c.test_point_id
            if pid not in groups:
                groups[pid] = []
            groups[pid].append(c)
        
        result = []
        for point in test_points:
            pid = point.id
            group = groups.get(pid, [])
            
            if not group:
                continue
            
            result.append(group[0])
            seen_names = {group[0].case_name}
            
            for c in group[1:]:
                if c.case_name not in seen_names:
                    seen_names.add(c.case_name)
                    result.append(c)
        
        return result
    
    def _fill_missing_points(
        self,
        cases: List[TestCase],
        test_points: List[TestPoint]
    ) -> List[TestCase]:
        """为缺失的测试点创建占位用例"""
        covered_ids = {c.test_point_id for c in cases}
        
        max_num = 0
        for c in cases:
            if c.case_id and c.case_id.startswith("TC"):
                try:
                    num = int(c.case_id[2:])
                    max_num = max(max_num, num)
                except ValueError:
                    pass
        
        placeholder_num = max_num + 1
        
        for point in test_points:
            if point.id not in covered_ids:
                placeholder = TestCase(
                    case_id=f"TC{placeholder_num:03d}",
                    case_name=f"【待补充】测试点{point.id}",
                    module="未分类",
                    test_point_id=point.id,
                    precondition="【请手动补充】",
                    steps=f"【请手动补充】\n\n原始测试点：{point.title[:100]}",
                    test_data="【请手动补充】",
                    expected="【请手动补充】",
                    is_placeholder=True,
                )
                cases.append(placeholder)
                placeholder_num += 1
        
        return cases
    
    def _create_placeholder(self, point: TestPoint) -> TestCase:
        """创建占位用例"""
        return TestCase(
            case_id=f"TC{point.id:03d}",
            case_name=f"【待补充】测试点{point.id}",
            module="未分类",
            test_point_id=point.id,
            precondition="【请手动补充】",
            steps=f"【请手动补充】\n\n原始测试点：{point.title[:100]}",
            test_data="【请手动补充】",
            expected="【请手动补充】",
            is_placeholder=True,
        )