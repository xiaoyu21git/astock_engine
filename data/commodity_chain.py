"""
商品价格传导分析模块
分析商品价格变化对产业链上下游的影响
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CommodityChainAnalyzer:
    """商品产业链分析器"""
    
    # 完整的产业链映射关系
    INDUSTRY_CHAIN = {
        # 黑色产业链
        'steel_chain': {
            'name': '钢铁产业链',
            'upstream': {  # 上游原材料
                'commodities': ['I', 'J'],  # 铁矿石、焦炭
                'stocks': {
                    'I': ['600808.SH', '600117.SH'],  # 马钢股份、西宁特钢
                    'J': ['600740.SH', '000983.SZ']   # 山西焦化、山西焦煤
                },
                'impact': 'negative'  # 原材料涨价是成本，负面影响
            },
            'midstream': {  # 中游生产
                'commodities': ['RB', 'HC'],  # 螺纹钢、热轧卷板
                'stocks': [
                    '600019.SH',  # 宝钢股份
                    '000709.SZ',  # 河钢股份
                    '000708.SZ',  # 中信特钢
                    '600005.SH',  # 武钢股份
                    '000898.SZ',  # 鞍钢股份
                ],
                'impact': 'positive'  # 产品涨价利好
            },
            'downstream': {  # 下游应用
                'industries': ['建筑', '机械', '汽车'],
                'stocks': [
                    '600585.SH',  # 海螺水泥
                    '000425.SZ',  # 徐工机械
                    '600031.SH',  # 三一重工
                ],
                'impact': 'negative'  # 原材料成本上升
            }
        },
        
        # 能源化工产业链
        'petrochemical_chain': {
            'name': '石油化工产业链',
            'upstream': {
                'commodities': ['SC', 'FU'],  # 原油、燃料油
                'stocks': [
                    '600028.SH',  # 中国石化
                    '601857.SH',  # 中国石油
                    '600688.SH',  # 上海石化
                ],
                'impact': 'complex'  # 既是成本也是产品
            },
            'midstream': {
                'commodities': ['TA', 'PTA', 'EG', 'PP'],  # PTA、乙二醇、聚丙烯
                'stocks': [
                    '000301.SZ',  # 东方盛虹
                    '601233.SH',  # 桐昆股份
                    '000059.SZ',  # 华锦股份
                    '600346.SH',  # 恒力石化
                ],
                'impact': 'positive'
            },
            'downstream': {
                'industries': ['纺织', '塑料制品', '包装'],
                'stocks': [
                    '600398.SH',  # 海澜之家
                    '002254.SZ',  # 泰和新材
                    '002493.SZ',  # 荣盛石化
                ],
                'impact': 'negative'
            }
        },
        
        # 有色金属产业链
        'metal_chain': {
            'name': '有色金属产业链',
            'upstream': {
                'commodities': ['CU', 'AL', 'ZN', 'NI'],  # 铜、铝、锌、镍
                'stocks': [
                    '601600.SH',  # 中国铝业
                    '000630.SZ',  # 铜陵有色
                    '600219.SH',  # 南山铝业
                    '000060.SZ',  # 中金岭南
                    '600362.SH',  # 江西铜业
                ],
                'impact': 'positive'
            },
            'downstream': {
                'industries': ['电子', '家电', '新能源'],
                'stocks': [
                    '002475.SZ',  # 立讯精密
                    '000333.SZ',  # 美的集团
                    '300750.SZ',  # 宁德时代
                ],
                'impact': 'negative'
            }
        },
        
        # 农产品产业链
        'agriculture_chain': {
            'name': '农产品产业链',
            'upstream': {
                'commodities': ['M', 'C', 'A'],  # 豆粕、玉米、豆一
                'stocks': [],  # 主要是进口
                'impact': 'negative'
            },
            'downstream': {
                'industries': ['饲料', '养殖', '食品'],
                'stocks': [
                    '000876.SZ',  # 新希望
                    '002311.SZ',  # 海大集团
                    '002714.SZ',  # 牧原股份
                    '000895.SZ',  # 双汇发展
                    '600887.SH',  # 伊利股份
                ],
                'impact': 'negative'  # 饲料成本上升
            }
        },
        
        # 煤炭电力产业链
        'coal_power_chain': {
            'name': '煤电产业链',
            'upstream': {
                'commodities': ['ZC', 'J'],  # 动力煤、焦炭
                'stocks': [
                    '601088.SH',  # 中国神华
                    '601898.SH',  # 中煤能源
                    '600188.SH',  # 兖矿能源
                ],
                'impact': 'positive'
            },
            'downstream': {
                'industries': ['电力'],
                'stocks': [
                    '600025.SH',  # 华能国际
                    '600011.SH',  # 华能水电
                    '600900.SH',  # 长江电力
                ],
                'impact': 'negative'  # 燃料成本上升
            }
        },
        
        # 新能源产业链
        'new_energy_chain': {
            'name': '新能源产业链',
            'upstream': {
                'commodities': ['LI', 'CO', 'NI'],  # 锂、钴、镍（期货代码）
                'stocks': [
                    '002460.SZ',  # 赣锋锂业
                    '002466.SZ',  # 天齐锂业
                    '603993.SH',  # 洛阳钼业
                ],
                'impact': 'positive'
            },
            'midstream': {
                'industries': ['电池材料'],
                'stocks': [
                    '300750.SZ',  # 宁德时代
                    '002812.SZ',  # 恩捷股份
                    '300014.SZ',  # 亿纬锂能
                ],
                'impact': 'negative'  # 原材料成本
            },
            'downstream': {
                'industries': ['新能源汽车', '光伏'],
                'stocks': [
                    '002594.SZ',  # 比亚迪
                    '601012.SH',  # 隆基绿能
                    '688599.SH',  # 天合光能
                ],
                'impact': 'negative'
            }
        }
    }
    
    # 商品价格阈值配置
    PRICE_THRESHOLDS = {
        'significant_change': 0.05,  # 5%以上为显著变化
        'major_change': 0.10,        # 10%以上为重大变化
        'extreme_change': 0.20,      # 20%以上为极端变化
    }
    
    def __init__(self):
        """初始化分析器"""
        self.price_history = {}
        
    def analyze_commodity_impact(self, 
                                 commodity_prices: pd.DataFrame,
                                 lookback_days: int = 30) -> Dict[str, List[Dict]]:
        """
        分析商品价格变化对产业链的影响
        
        Args:
            commodity_prices: 商品价格数据
                columns: ['commodity', 'date', 'close', 'pct_change']
            lookback_days: 回看天数
            
        Returns:
            影响分析结果
        """
        impacts = {
            'upstream_benefits': [],   # 上游受益
            'midstream_benefits': [],  # 中游受益
            'downstream_pressure': [], # 下游压力
            'cost_pass_through': []    # 成本传导
        }
        
        for chain_name, chain_data in self.INDUSTRY_CHAIN.items():
            # 分析上游
            if 'upstream' in chain_data:
                upstream_impacts = self._analyze_chain_segment(
                    commodity_prices,
                    chain_data['upstream'],
                    'upstream',
                    chain_data['name']
                )
                impacts['upstream_benefits'].extend(upstream_impacts)
            
            # 分析中游
            if 'midstream' in chain_data:
                midstream_impacts = self._analyze_chain_segment(
                    commodity_prices,
                    chain_data['midstream'],
                    'midstream',
                    chain_data['name']
                )
                impacts['midstream_benefits'].extend(midstream_impacts)
            
            # 分析下游
            if 'downstream' in chain_data:
                downstream_impacts = self._analyze_chain_segment(
                    commodity_prices,
                    chain_data['downstream'],
                    'downstream',
                    chain_data['name']
                )
                impacts['downstream_pressure'].extend(downstream_impacts)
        
        return impacts
    
    def _analyze_chain_segment(self, 
                               commodity_prices: pd.DataFrame,
                               segment_data: Dict,
                               segment_type: str,
                               chain_name: str) -> List[Dict]:
        """分析产业链某一环节"""
        impacts = []
        
        if 'commodities' not in segment_data:
            return impacts
        
        for commodity in segment_data['commodities']:
            commodity_data = commodity_prices[commodity_prices['commodity'] == commodity]
            
            if commodity_data.empty:
                continue
            
            # 获取价格变化
            latest_data = commodity_data.iloc[-1]
            pct_change = latest_data.get('pct_change', 0)
            
            # 判断变化程度
            if abs(pct_change) < self.PRICE_THRESHOLDS['significant_change']:
                continue
            
            change_level = self._classify_price_change(abs(pct_change))
            impact_direction = segment_data.get('impact', 'positive')
            
            # 确定影响
            if impact_direction == 'positive':
                actual_impact = 'positive' if pct_change > 0 else 'negative'
            elif impact_direction == 'negative':
                actual_impact = 'negative' if pct_change > 0 else 'positive'
            else:  # complex
                actual_impact = 'complex'
            
            # 获取相关股票
            stocks = segment_data.get('stocks', [])
            if isinstance(stocks, dict):
                stocks = stocks.get(commodity, [])
            
            impacts.append({
                'chain': chain_name,
                'segment': segment_type,
                'commodity': commodity,
                'price_change': pct_change,
                'change_level': change_level,
                'impact_direction': actual_impact,
                'affected_stocks': stocks,
                'timestamp': datetime.now()
            })
        
        return impacts
    
    def _classify_price_change(self, abs_change: float) -> str:
        """分类价格变化程度"""
        if abs_change >= self.PRICE_THRESHOLDS['extreme_change']:
            return 'extreme'
        elif abs_change >= self.PRICE_THRESHOLDS['major_change']:
            return 'major'
        elif abs_change >= self.PRICE_THRESHOLDS['significant_change']:
            return 'significant'
        else:
            return 'normal'
    
    def get_price_transmission_path(self, commodity: str) -> List[Dict]:
        """
        获取商品价格传导路径
        
        Args:
            commodity: 商品代码
            
        Returns:
            传导路径列表
        """
        paths = []
        
        for chain_name, chain_data in self.INDUSTRY_CHAIN.items():
            path = {
                'chain': chain_data['name'],
                'stages': []
            }
            
            # 检查是否包含该商品
            found = False
            
            for stage_name in ['upstream', 'midstream', 'downstream']:
                if stage_name not in chain_data:
                    continue
                
                stage_data = chain_data[stage_name]
                commodities = stage_data.get('commodities', [])
                
                if commodity in commodities or (isinstance(commodities, dict) and commodity in commodities.values()):
                    found = True
                    path['stages'].append({
                        'stage': stage_name,
                        'impact': stage_data.get('impact', 'neutral'),
                        'stocks': stage_data.get('stocks', [])
                    })
            
            if found:
                paths.append(path)
        
        return paths
    
    def calculate_cost_pressure_index(self, 
                                     commodity_prices: pd.DataFrame,
                                     industry: str) -> float:
        """
        计算行业成本压力指数
        
        Args:
            commodity_prices: 商品价格数据
            industry: 行业名称
            
        Returns:
            成本压力指数 (0-1，越高压力越大)
        """
        pressure_scores = []
        
        for chain_name, chain_data in self.INDUSTRY_CHAIN.items():
            if chain_data['name'] != industry:
                continue
            
            # 检查上游原材料价格变化
            if 'upstream' in chain_data:
                upstream = chain_data['upstream']
                for commodity in upstream.get('commodities', []):
                    commodity_data = commodity_prices[commodity_prices['commodity'] == commodity]
                    if not commodity_data.empty:
                        pct_change = commodity_data.iloc[-1].get('pct_change', 0)
                        if pct_change > 0:  # 原材料涨价
                            pressure_scores.append(min(pct_change * 2, 1.0))
        
        return np.mean(pressure_scores) if pressure_scores else 0.0
    
    def find_beneficiary_stocks(self, 
                               commodity: str,
                               price_trend: str) -> List[str]:
        """
        找出商品价格变化的受益股票
        
        Args:
            commodity: 商品代码
            price_trend: 'up' or 'down'
            
        Returns:
            受益股票列表
        """
        beneficiaries = []
        
        for chain_name, chain_data in self.INDUSTRY_CHAIN.items():
            for stage_name, stage_data in chain_data.items():
                if stage_name not in ['upstream', 'midstream', 'downstream']:
                    continue
                
                if 'commodities' not in stage_data:
                    continue
                
                commodities = stage_data['commodities']
                if commodity not in commodities:
                    continue
                
                impact = stage_data.get('impact', 'neutral')
                
                # 判断是否受益
                is_beneficiary = False
                if price_trend == 'up' and impact == 'positive':
                    is_beneficiary = True
                elif price_trend == 'down' and impact == 'negative':
                    is_beneficiary = True
                
                if is_beneficiary:
                    stocks = stage_data.get('stocks', [])
                    if isinstance(stocks, dict):
                        stocks = stocks.get(commodity, [])
                    beneficiaries.extend(stocks)
        
        return list(set(beneficiaries))  # 去重
    
    def generate_commodity_report(self, 
                                 commodity_prices: pd.DataFrame) -> str:
        """
        生成商品价格传导分析报告
        
        Args:
            commodity_prices: 商品价格数据
            
        Returns:
            分析报告文本
        """
        report = []
        report.append("=" * 60)
        report.append("商品价格传导分析报告")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 60)
        
        # 分析影响
        impacts = self.analyze_commodity_impact(commodity_prices)
        
        # 上游受益
        if impacts['upstream_benefits']:
            report.append("\n【上游原材料受益】")
            for impact in impacts['upstream_benefits'][:5]:
                report.append(f"  • {impact['commodity']}: {impact['price_change']:+.2%}, "
                            f"影响 {len(impact['affected_stocks'])} 只股票")
        
        # 中游受益
        if impacts['midstream_benefits']:
            report.append("\n【中游生产受益】")
            for impact in impacts['midstream_benefits'][:5]:
                report.append(f"  • {impact['chain']}: {impact['commodity']} "
                            f"{impact['price_change']:+.2%}")
        
        # 下游压力
        if impacts['downstream_pressure']:
            report.append("\n【下游应用承压】")
            for impact in impacts['downstream_pressure'][:5]:
                report.append(f"  • {impact['chain']}: 成本压力上升")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
