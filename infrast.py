import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field



@dataclass
class Operator:
    id: str
    name: str
    elite: int
    level: int
    own: bool
    potential: int
    rarity: int


@dataclass
class ControlCenterRequirement:
    operator: str
    elite_required: int


@dataclass
class DormitoryRequirement:
    operator: str
    elite_required: int


@dataclass
class PowerStationRequirement:
    operator: str
    elite_required: int


@dataclass
class OperatorEfficiency:
    operators: List[str]
    workplace_type: str
    base_efficiency: float
    synergy_efficiency: float
    description: str
    elite_requirements: Dict[str, int]
    requires_control_center: List[ControlCenterRequirement]
    requires_dormitory: List[DormitoryRequirement]
    requires_power_station: List[PowerStationRequirement]  # 新增
    special_conditions: Optional[str] = None
    apply_each: bool = False
    priority: int = 0
    products: List[str] = field(default_factory=list)


@dataclass
class Workplace:
    id: str
    name: str
    max_operators: int
    base_efficiency: float
    products: List[str] = field(default_factory=list)  # 保留，支持验证
    current_product: str = ""  # 新增，当前班次产物


@dataclass
class AssignmentResult:
    workplace: Workplace
    optimal_operators: List[Operator]
    total_efficiency: float
    operator_efficiency: float
    applied_combinations: List[str]
    control_center_requirements: List[ControlCenterRequirement]
    dormitory_requirements: List[DormitoryRequirement]
    power_station_requirements: List[PowerStationRequirement]  # 新增


class WorkplaceOptimizer:
    def __init__(self, efficiency_file: str, operator_file: str, config_file: str = None, debug: bool = False):
        # 保存文件名，便于调试输出
        self.efficiency_file = efficiency_file
        self.operator_file = operator_file
        self.config_file = config_file
        self.debug = debug

        self.efficiency_data = self.load_json(efficiency_file)
        self.operator_data = self.load_json(operator_file)
        self.config_data = self.load_json(config_file) if config_file else {}

        # 从 config.json 读取数量，默认 3 和 3
        self.trading_stations_count = self.config_data.get('trading_stations_count', 3)
        self.manufacturing_stations_count = self.config_data.get('manufacturing_stations_count', 3)

        self.operators = self.load_operators()
        self.efficiency_rules = self.load_efficiency_rules()
        self.workplaces = self.load_workplaces()
        self.fiammetta_targets = []  # 修改：当前菲亚梅塔目标列表

        # 如果启用调试模式，打印加载信息和摘要
        if self.debug:
            self.print_loaded_files()
            self.print_operator_summary()
            self.print_efficiency_rules(limit=20)
            self.print_workplaces()

    def load_json(self, file_path: str) -> Any:
        """加载JSON文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            print("加载文件:", file_path)
            return json.load(f)

    def load_operators(self) -> Dict[str, Operator]:
        """加载干员配置"""
        operators = {}
        for op_data in self.operator_data:
            operators[op_data['name']] = Operator(
                id=op_data['id'],
                name=op_data['name'],
                elite=op_data['elite'],
                level=op_data['level'],
                own=op_data['own'],
                potential=op_data['potential'],
                rarity=op_data['rarity']
            )
        return operators

    # 在 load_efficiency_rules 方法中更新解析逻辑
    def load_efficiency_rules(self) -> List[OperatorEfficiency]:
        expanded_rules: List[OperatorEfficiency] = []

        def parse_operator_string(op_str: str) -> tuple[str, int]:
            if '/' in op_str:
                name, elite_str = op_str.split('/', 1)
                return name.strip(), int(elite_str.strip())
            else:
                return op_str.strip(), 0

        for workplace_type, systems in self.efficiency_data.get('combination_rules', {}).items():
            for system_name, system_data in systems.items():
                if isinstance(system_data, list):
                    # 直接是规则列表，如 "通用组合"、"通用单人"
                    for rule_data in system_data:
                        operators = []
                        elite_requirements = {}
                        for op_str in rule_data['combo']:
                            name, elite = parse_operator_string(op_str)
                            operators.append(name)
                            if elite > 0:
                                elite_requirements[name] = elite

                        control_center_reqs = []
                        dormitory_reqs = []
                        power_station_reqs = []
                        if 'control_center' in rule_data:
                            for cc_str in rule_data['control_center']:
                                name, elite = parse_operator_string(cc_str)
                                control_center_reqs.append(ControlCenterRequirement(operator=name, elite_required=elite))
                        if 'dormitory' in rule_data:
                            for dorm_str in rule_data['dormitory']:
                                name, elite = parse_operator_string(dorm_str)
                                dormitory_reqs.append(DormitoryRequirement(operator=name, elite_required=elite))
                        if 'power_station' in rule_data:
                            for pow_str in rule_data['power_station']:
                                op_name, elite = parse_operator_string(pow_str)
                                power_station_reqs.append(PowerStationRequirement(operator=op_name, elite_required=elite))

                        description = "通用单人" if rule_data.get('apply_each', False) else f"{system_name} - {', '.join(operators)}"

                        # 解析产物（默认为空列表）
                        rule_products = rule_data.get('product', [])
                        if isinstance(rule_products, str):
                            rule_products = [rule_products]

                        expanded_rules.append(OperatorEfficiency(
                            operators=operators,
                            workplace_type=workplace_type,
                            base_efficiency=0,
                            synergy_efficiency=rule_data['efficiency'],
                            description=description,
                            elite_requirements=elite_requirements,
                            requires_control_center=control_center_reqs,
                            requires_dormitory=dormitory_reqs,
                            requires_power_station=power_station_reqs,
                            special_conditions=None,
                            apply_each=rule_data.get('apply_each', False),
                            priority=rule_data.get('priority', 0),
                            products=rule_products  # 新增
                        ))

                elif isinstance(system_data, dict):
                    # 处理有 base_combo 的体系，如 "巫恋组"、"但书体系"、"孑体系"
                    base_operators = []
                    base_elite_requirements = {}
                    base_products = system_data.get('product', [])  # 基础产物
                    if isinstance(base_products, str):
                        base_products = [base_products]

                    if 'base_combo' in system_data:
                        for op_str in system_data['base_combo']:
                            name, elite = parse_operator_string(op_str)
                            base_operators.append(name)
                            if elite > 0:
                                base_elite_requirements[name] = elite

                    for rule_data in system_data.get('rules', []):
                        all_operators = base_operators.copy()
                        all_elite_requirements = base_elite_requirements.copy()

                        for op_str in rule_data.get('combo', []):
                            name, elite = parse_operator_string(op_str)
                            all_operators.append(name)
                            if elite > 0:
                                all_elite_requirements[name] = elite

                        control_center_reqs = []
                        dormitory_reqs = []
                        power_station_reqs = []
                        if 'control_center' in rule_data:
                            for cc_str in rule_data['control_center']:
                                name, elite = parse_operator_string(cc_str)
                                control_center_reqs.append(
                                    ControlCenterRequirement(operator=name, elite_required=elite))
                        if 'dormitory' in rule_data:
                            for dorm_str in rule_data['dormitory']:
                                name, elite = parse_operator_string(dorm_str)
                                dormitory_reqs.append(DormitoryRequirement(operator=name, elite_required=elite))
                        if 'power_station' in rule_data:
                            for pow_str in rule_data['power_station']:
                                op_name, elite = parse_operator_string(pow_str)
                                power_station_reqs.append(PowerStationRequirement(operator=op_name, elite_required=elite))

                        # 合并基础和规则产物
                        rule_products = rule_data.get('product', base_products)
                        if isinstance(rule_products, str):
                            rule_products = [rule_products]
                        elif not isinstance(rule_products, list):
                            rule_products = base_products

                        description = f"{system_name} - {', '.join(all_operators)}"
                        expanded_rules.append(OperatorEfficiency(
                            operators=all_operators,
                            workplace_type=workplace_type,
                            base_efficiency=0,
                            synergy_efficiency=rule_data['efficiency'],
                            description=description,
                            elite_requirements=all_elite_requirements,
                            requires_control_center=control_center_reqs,
                            requires_dormitory=dormitory_reqs,
                            special_conditions=None,
                            apply_each=rule_data.get('apply_each', False),
                            priority=rule_data.get('priority', 0),
                            products=rule_products,
                            requires_power_station=power_station_reqs  # 新增
                        ))

        expanded_rules.sort(key=lambda r: (r.priority, r.synergy_efficiency), reverse=True)

        if self.debug:
            print(f"DEBUG: 加载并解析新结构效率规则，总计 {len(expanded_rules)} 条")

        return expanded_rules

    def load_workplaces(self) -> Dict[str, List[Workplace]]:
        workplaces = {
            'trading_stations': [],
            'manufacturing_stations': [],
            'meeting_room': [],
            'power_station': []
        }

        # 从 efficiency.json 取默认值（第一个工作站）
        default_trading = self.efficiency_data['workplaces']['trading_stations'][0] if \
        self.efficiency_data['workplaces']['trading_stations'] else {'max_operators': 3, 'base_efficiency': 100}
        default_manufacturing = self.efficiency_data['workplaces']['manufacturing_stations'][0] if \
        self.efficiency_data['workplaces']['manufacturing_stations'] else {'max_operators': 3, 'base_efficiency': 100}

        # 动态创建贸易站
        for i in range(self.trading_stations_count):
            workplaces['trading_stations'].append(Workplace(
                id=f"trading_{i + 1}",
                name=f"贸易站{i + 1}",
                max_operators=default_trading['max_operators'],
                base_efficiency=default_trading['base_efficiency']
            ))

        # 动态创建制造站
        for i in range(self.manufacturing_stations_count):
            workplaces['manufacturing_stations'].append(Workplace(
                id=f"manufacturing_{i + 1}",
                name=f"制造站{i + 1}",
                max_operators=default_manufacturing['max_operators'],
                base_efficiency=default_manufacturing['base_efficiency']
            ))

        # 添加会客室
        meeting_data = self.efficiency_data['workplaces']['meeting_room']
        workplaces['meeting_room'].append(Workplace(
            id=meeting_data['id'],
            name=meeting_data['name'],
            max_operators=meeting_data['max_operators'],
            base_efficiency=meeting_data['base_efficiency']
        ))

        # 添加发电站
        power_stations = self.efficiency_data['workplaces']['power_station']
        for ps_data in power_stations:
            workplaces['power_station'].append(Workplace(
                id=ps_data['id'],
                name=ps_data['name'],
                max_operators=ps_data['max_operators'],
                base_efficiency=ps_data['base_efficiency']
            ))

        return workplaces

    def get_available_operators(self) -> List[Operator]:
        """获取可用的干员列表（拥有的干员）"""
        return [op for op in self.operators.values() if op.own]

    def check_elite_requirements(self, operators: List[Operator], elite_requirements: Dict[str, int]) -> bool:
        """检查干员是否满足精英化要求"""
        operator_dict = {op.name: op for op in operators}

        for op_name, required_elite in elite_requirements.items():
            if op_name in operator_dict:
                if operator_dict[op_name].elite < required_elite:
                    return False
        return True

    def check_control_center_requirements(self, control_center_reqs: List[ControlCenterRequirement]) -> bool:
        """检查中枢需求是否满足：动态判断干员是否拥有且精英等级满足"""
        for req in control_center_reqs:
            if req.operator not in self.operators:
                return False
            op = self.operators[req.operator]
            if not op.own or op.elite < req.elite_required:
                return False
        return True

    def check_dormitory_requirements(self, dormitory_reqs: List[DormitoryRequirement]) -> bool:
        """检查宿舍需求是否满足"""
        for req in dormitory_reqs:
            if req.operator not in self.operators:
                return False
            op = self.operators[req.operator]
            if not op.own or op.elite < req.elite_required:
                return False
        return True

    def check_power_station_requirements(self, dormitory_reqs: List[PowerStationRequirement]) -> bool:
        """检查宿舍需求是否满足"""
        for req in dormitory_reqs:
            if req.operator not in self.operators:
                return False
            op = self.operators[req.operator]
            if not op.own or op.elite < req.elite_required:
                return False
        return True

    def check_fiammetta_available(self) -> bool:
        """检查菲亚梅塔是否可用（拥有且精二）"""
        if '菲亚梅塔' not in self.operators:
            return False
        op = self.operators['菲亚梅塔']
        return op.own and op.elite >= 2

    def get_workplace_type(self, workplace: Workplace) -> str:
        if 'trading' in workplace.id:
            return 'trading_station'
        elif 'manufacturing' in workplace.id:
            return 'manufacturing_station'
        elif 'meeting' in workplace.id:
            return 'meeting_room'
        elif 'power' in workplace.id:
            return 'power_station'
        else:
            return workplace.id.split('_')[0] + '_station'[0] + '_station'

    def calculate_combination_efficiency(self, operators: List[Operator], workplace_type: str) -> tuple[
        float, List[str], List[ControlCenterRequirement]]:
        """计算干员组合的效率和应用的组合"""
        total_efficiency = 0
        applied_combinations = []
        applied_control_center_reqs = []
        used_operator_names = [op.name for op in operators]

        if self.debug:
            print(f"DEBUG: 计算组合效率 -> 工作站类型: {workplace_type}, 干员: {used_operator_names}")

        # 检查所有可能的组合
        for rule in self.efficiency_rules:
            if rule.workplace_type != workplace_type:
                continue

            # 检查是否满足组合条件
            if all(op_name in used_operator_names for op_name in rule.operators):
                # 检查精英化要求
                if not self.check_elite_requirements(operators, rule.elite_requirements):
                    if self.debug:
                        print(f"DEBUG: 精英化不满足，跳过规则: {rule.description}")
                    continue

                # 检查中枢需求
                if not self.check_control_center_requirements(rule.requires_control_center):
                    if self.debug:
                        cc = ','.join([f"{r.operator}(精{r.elite_required})" for r in rule.requires_control_center])
                        print(f"DEBUG: 中枢需求不满足({cc})，跳过规则: {rule.description}")
                    continue

                # 检查宿舍需求
                if not self.check_dormitory_requirements(rule.requires_dormitory):
                    if self.debug:
                        dorm_reqs = [f"{r.operator}(精{r.elite_required})" for r in rule.requires_dormitory]
                        print(f"DEBUG: 宿舍需求不满足({dorm_reqs})，跳过规则: {rule.description}")
                    continue

                # 所有条件满足，应用该组合
                total_efficiency += rule.synergy_efficiency
                applied_combinations.append(rule.description)
                applied_control_center_reqs.extend(rule.requires_control_center)
                if self.debug:
                    print(f"DEBUG: 生效规则: {rule.description} -> +{rule.synergy_efficiency}%")

        # 如果没有组合效果，计算个体效率
        if total_efficiency == 0:
            for op in operators:
                # 这里可以添加个体效率计算逻辑
                individual_eff = 0  # 从individual_efficiencies获取
                total_efficiency += individual_eff

        if self.debug:
            print(f"DEBUG: 组合最终效率: {total_efficiency}% (只计算干员贡献，不含基地基础)")

        return total_efficiency, applied_combinations, applied_control_center_reqs

    def optimize_workplace(self, workplace: Workplace, operator_usage: Dict[str, int],
                           shift_used_names: set) -> AssignmentResult:
        """优化单个工作站的干员配置（体系优先 + 通用替补），考虑全局干员使用限制和班次内重复限制。

        每个干员一天最多分配到两个班次，除菲亚梅塔目标可3班。
        """
        available_ops = self.get_available_operators()
        op_by_name = {op.name: op for op in available_ops}
        workplace_type = self.get_workplace_type(workplace)

        # 过滤规则：如果规则指定产物，则必须匹配当前产物；未指定则允许
        def rule_matches_products(rule: OperatorEfficiency) -> bool:
            if not rule.products:
                return True
            return workplace.current_product in rule.products

        if self.debug:
            print(
                f"DEBUG: 开始优化站点 {workplace.name} ({workplace.id})，站点可放: {workplace.max_operators}")

        remaining_slots = workplace.max_operators
        assigned_ops: List[Operator] = []
        used_names = set()
        total_synergy = 0.0
        applied_combinations: List[str] = []
        applied_control_center_reqs: List[ControlCenterRequirement] = []
        applied_dormitory_reqs: List[DormitoryRequirement] = []
        applied_power_station_reqs: List[PowerStationRequirement] = []

        # 收集所有可用的规则（包括特定体系和通用规则）
        all_rules = [r for r in self.efficiency_rules if
                     r.workplace_type == workplace_type and
                     rule_matches_products(r)]

        # 按体系分组
        system_groups = {}
        for rule in all_rules:
            # 确定规则所属的体系
            system_name = "通用"
            for sys_key in self.efficiency_data['combination_rules'].get(workplace_type, {}):
                if sys_key in rule.description:
                    system_name = sys_key
                    break

            if system_name not in system_groups:
                system_groups[system_name] = []
            system_groups[system_name].append(rule)

        # 在每个体系组内按权重排序
        for system_name, rules in system_groups.items():
            rules.sort(key=lambda r: (r.priority, r.synergy_efficiency), reverse=True)

        # 评估所有可能的组合方案
        best_candidate = None
        best_efficiency = -1

        # 评估特定体系组合
        for system_name, rules in system_groups.items():
            if system_name == "通用":
                continue  # 通用规则单独处理

            for rule in rules:
                if remaining_slots <= 0:
                    break

                required = rule.operators
                if self.debug:
                    print(f"DEBUG: 评估体系规则: {rule.description}")

                # 检查干员可用性
                unavailable_ops = []
                for op_name in required:
                    max_usage = 3 if op_name in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                    if (op_name not in op_by_name or
                            op_name in used_names or
                            op_name in shift_used_names or
                            operator_usage.get(op_name, 0) >= max_usage):
                        unavailable_ops.append(op_name)

                if unavailable_ops:
                    if self.debug:
                        print(f"DEBUG:  干员不可用: {unavailable_ops}")
                    continue

                if len(required) > remaining_slots:
                    if self.debug:
                        print(f"DEBUG:  所需槽位({len(required)}) > 剩余槽位({remaining_slots})")
                    continue

                op_objs = [op_by_name[op_name] for op_name in required]
                if not self.check_elite_requirements(op_objs, rule.elite_requirements):
                    if self.debug:
                        print(f"DEBUG:  精英要求不满足: {rule.elite_requirements}")
                    continue

                if not self.check_control_center_requirements(rule.requires_control_center):
                    if self.debug:
                        cc_reqs = [f"{r.operator}(精{r.elite_required})" for r in rule.requires_control_center]
                        print(f"DEBUG:  中枢需求不满足: {cc_reqs}")
                    continue

                # 检查宿舍需求
                if not self.check_dormitory_requirements(rule.requires_dormitory):
                    if self.debug:
                        dorm_reqs = [f"{r.operator}(精{r.elite_required})" for r in rule.requires_dormitory]
                        print(f"DEBUG: 宿舍需求不满足({dorm_reqs})，跳过规则: {rule.description}")
                    continue

                if not self.check_power_station_requirements(rule.requires_power_station):
                    if self.debug:
                        power_reqs = [f"{r.operator}(精{r.elite_required})" for r in rule.requires_power_station]
                        print(f"DEBUG: 发电站需求不满足({power_reqs})，跳过规则: {rule.description}")
                    continue

                # 计算效率（人均效率）
                efficiency_per_slot = rule.synergy_efficiency / len(required)
                if efficiency_per_slot > best_efficiency:
                    best_efficiency = efficiency_per_slot
                    best_candidate = {
                        'type': 'system',
                        'rule': rule,
                        'required': required,
                        'efficiency': rule.synergy_efficiency,
                        'slots_used': len(required)
                    }

        # 评估通用规则（包括apply_each）
        generic_rules = system_groups.get("通用", [])
        for rule in generic_rules:
            if remaining_slots <= 0:
                break

            if rule.apply_each:
                # 对于apply_each规则，评估每个可用干员的效率
                for op_name in rule.operators:
                    max_usage = 3 if op_name in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                    if (remaining_slots <= 0 or
                            op_name in used_names or
                            op_name in shift_used_names or
                            op_name not in op_by_name or
                            operator_usage.get(op_name, 0) >= max_usage):
                        continue

                    op_obj = op_by_name[op_name]
                    req_elite = {op_name: rule.elite_requirements.get(op_name, 0)}
                    if (not self.check_elite_requirements([op_obj], req_elite) or
                            not self.check_control_center_requirements(rule.requires_control_center)):
                        continue

                    efficiency_per_slot = rule.synergy_efficiency
                    if efficiency_per_slot > best_efficiency:
                        best_efficiency = efficiency_per_slot
                        best_candidate = {
                            'type': 'generic_each',
                            'rule': rule,
                            'required': [op_name],
                            'efficiency': rule.synergy_efficiency,
                            'slots_used': 1
                        }
            else:
                # 对于普通通用规则
                required = rule.operators
                max_usage_check = lambda \
                    op_name: 3 if op_name in self.fiammetta_targets and workplace_type == 'trading_station' else 2

                if any(op_name not in op_by_name or
                       op_name in used_names or
                       op_name in shift_used_names or
                       operator_usage.get(op_name, 0) >= max_usage_check(op_name)
                       for op_name in required) or len(required) > remaining_slots:
                    continue

                op_objs = [op_by_name[op_name] for op_name in required]
                if (not self.check_elite_requirements(op_objs, rule.elite_requirements) or
                        not self.check_control_center_requirements(rule.requires_control_center)):
                    continue

                efficiency_per_slot = rule.synergy_efficiency / len(required)
                if efficiency_per_slot > best_efficiency:
                    best_efficiency = efficiency_per_slot
                    best_candidate = {
                        'type': 'generic',
                        'rule': rule,
                        'required': required,
                        'efficiency': rule.synergy_efficiency,
                        'slots_used': len(required)
                    }

        # 应用最佳候选方案
        if best_candidate and best_efficiency > 0:
            rule = best_candidate['rule']
            required = best_candidate['required']

            for op_name in required:
                assigned_ops.append(op_by_name[op_name])
                used_names.add(op_name)
                shift_used_names.add(op_name)
                operator_usage[op_name] += 1

            remaining_slots -= best_candidate['slots_used']
            total_synergy += best_candidate['efficiency']

            if best_candidate['type'] == 'generic_each':
                applied_combinations.append(f"{rule.description}({', '.join(required)})")
            else:
                applied_combinations.append(rule.description)

            applied_control_center_reqs.extend(rule.requires_control_center)
            applied_dormitory_reqs.extend(rule.requires_dormitory)
            applied_power_station_reqs.extend(rule.requires_power_station)

            if self.debug:
                print(f"DEBUG: 应用最佳规则: {rule.description} -> +{rule.synergy_efficiency}%")

        # 递归处理剩余槽位
        if remaining_slots > 0:
            # 递归调用自身处理剩余槽位
            recursive_result = self.optimize_workplace_recursive(
                workplace, operator_usage, shift_used_names,
                assigned_ops, used_names, remaining_slots
            )

            assigned_ops.extend(recursive_result['assigned_ops'])
            total_synergy += recursive_result['total_synergy']
            applied_combinations.extend(recursive_result['applied_combinations'])
            applied_control_center_reqs.extend(recursive_result['applied_control_center_reqs'])
            applied_dormitory_reqs.extend(recursive_result['applied_dormitory_reqs'])
            applied_power_station_reqs.extend(recursive_result['applied_power_station_reqs'])

        # 返回结果
        if self.debug:
            names = ','.join([op.name for op in assigned_ops])
            print(f"DEBUG: 完成分配 {workplace.name}，分配: {names}，总干员增益: {total_synergy}%")

        return AssignmentResult(
            workplace=workplace,
            optimal_operators=assigned_ops,
            total_efficiency=workplace.base_efficiency + total_synergy,
            operator_efficiency=total_synergy,
            applied_combinations=applied_combinations,
            control_center_requirements=applied_control_center_reqs,
            dormitory_requirements=applied_dormitory_reqs,
            power_station_requirements=applied_power_station_reqs
        )

    def optimize_workplace_recursive(self, workplace: Workplace, operator_usage: Dict[str, int],
                                     shift_used_names: set, assigned_ops: List[Operator],
                                     used_names: set, remaining_slots: int) -> Dict[str, Any]:
        """递归优化工作站的剩余槽位"""
        available_ops = self.get_available_operators()
        op_by_name = {op.name: op for op in available_ops}
        workplace_type = self.get_workplace_type(workplace)

        total_synergy = 0.0
        applied_combinations = []
        applied_control_center_reqs = []
        applied_dormitory_reqs = []
        applied_power_station_reqs = []

        # 过滤规则：如果规则指定产物，则必须匹配当前产物；未指定则允许
        def rule_matches_products(rule: OperatorEfficiency) -> bool:
            if not rule.products:
                return True
            return workplace.current_product in rule.products

        while remaining_slots > 0:
            best_candidate = None
            best_efficiency = -1

            # 评估所有可用规则
            all_rules = [r for r in self.efficiency_rules if
                         r.workplace_type == workplace_type and
                         rule_matches_products(r)]

            for rule in all_rules:
                if rule.apply_each:
                    # 对于apply_each规则，评估每个可用干员
                    for op_name in rule.operators:
                        max_usage = 3 if op_name in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                        if (op_name in used_names or
                                op_name in shift_used_names or
                                op_name not in op_by_name or
                                operator_usage.get(op_name, 0) >= max_usage):
                            continue

                        op_obj = op_by_name[op_name]
                        req_elite = {op_name: rule.elite_requirements.get(op_name, 0)}
                        if (not self.check_elite_requirements([op_obj], req_elite) or
                                not self.check_control_center_requirements(rule.requires_control_center)):
                            continue

                        efficiency = rule.synergy_efficiency
                        if efficiency > best_efficiency:
                            best_efficiency = efficiency
                            best_candidate = {
                                'rule': rule,
                                'required': [op_name],
                                'efficiency': efficiency,
                                'slots_used': 1,
                                'type': 'each'
                            }
                else:
                    # 对于普通规则
                    required = rule.operators
                    if len(required) > remaining_slots:
                        continue

                    max_usage_check = lambda \
                        op_name: 3 if op_name in self.fiammetta_targets and workplace_type == 'trading_station' else 2
                    if any(op_name in used_names or
                           op_name in shift_used_names or
                           op_name not in op_by_name or
                           operator_usage.get(op_name, 0) >= max_usage_check(op_name)
                           for op_name in required):
                        continue

                    op_objs = [op_by_name[op_name] for op_name in required]
                    if (not self.check_elite_requirements(op_objs, rule.elite_requirements) or
                            not self.check_control_center_requirements(rule.requires_control_center)):
                        continue

                    efficiency_per_slot = rule.synergy_efficiency / len(required)
                    if efficiency_per_slot > best_efficiency:
                        best_efficiency = efficiency_per_slot
                        best_candidate = {
                            'rule': rule,
                            'required': required,
                            'efficiency': rule.synergy_efficiency,
                            'slots_used': len(required),
                            'type': 'normal'
                        }

            # 应用最佳候选
            if best_candidate and best_efficiency > 0:
                rule = best_candidate['rule']
                required = best_candidate['required']

                for op_name in required:
                    assigned_ops.append(op_by_name[op_name])
                    used_names.add(op_name)
                    shift_used_names.add(op_name)
                    operator_usage[op_name] += 1

                remaining_slots -= best_candidate['slots_used']
                total_synergy += best_candidate['efficiency']

                if best_candidate['type'] == 'each':
                    applied_combinations.append(f"{rule.description}({', '.join(required)})")
                else:
                    applied_combinations.append(rule.description)

                applied_control_center_reqs.extend(rule.requires_control_center)
                applied_dormitory_reqs.extend(rule.requires_dormitory)
                applied_power_station_reqs.extend(rule.requires_power_station)
            else:
                # 没有合适的规则，退出循环
                break

        return {
            'assigned_ops': [],
            'total_synergy': total_synergy,
            'applied_combinations': applied_combinations,
            'applied_control_center_reqs': applied_control_center_reqs,
            'applied_dormitory_reqs': applied_dormitory_reqs,
            'applied_power_station_reqs': applied_power_station_reqs
        }

    def get_optimal_assignments(self, product_requirements: Dict[str, Dict[str, int]] = None) -> Dict[str, Any]:
        """获取最优分配方案，输出符合 MAA 协议的 JSON 格式"""
        if product_requirements is None:
            product_requirements = self.config_data.get('product_requirements', {
                "trading_stations": {"LMD": 3, "Orundum": 0},  # 默认值，可调整
                "manufacturing_stations": {"Pure Gold": 3, "Originium Shard": 0, "Battle Record": 0}
            })

        fiammetta_config = self.config_data.get('Fiammetta', {"enable": False})
        fiammetta_enable = fiammetta_config.get('enable', False)
        fiammetta_available = self.check_fiammetta_available() if fiammetta_enable else False
        self.fiammetta_targets = self.select_fiammetta_targets() if fiammetta_available else []  # 设置类属性为列表
        if fiammetta_enable and not self.fiammetta_targets:
            fiammetta_enable = False  # 无可用目标，禁用

        # 设置贸易站产物
        trading_products = []
        for product, count in product_requirements['trading_stations'].items():
            trading_products.extend([product] * count)
        for i, workplace in enumerate(self.workplaces['trading_stations']):
            workplace.current_product = trading_products[i] if i < len(trading_products) else ""

        # 设置制造站产物
        manufacturing_products = []
        for product, count in product_requirements['manufacturing_stations'].items():
            manufacturing_products.extend([product] * count)
        for i, workplace in enumerate(self.workplaces['manufacturing_stations']):
            workplace.current_product = manufacturing_products[i] if i < len(manufacturing_products) else ""

        results = {
            "title": "优化换班方案",
            "description": "基于效率规则自动生成的换班方案",
            "plans": []
        }

        # 全局跟踪干员使用次数（最多2班，除菲亚梅塔目标可3班）
        operator_usage = {op.name: 0 for op in self.get_available_operators()}

        for shift in range(3):  # 3班
            current_target = self.fiammetta_targets[
                shift % len(self.fiammetta_targets)] if self.fiammetta_targets else ""

            plan = {
                "name": f"第{shift + 1}班",
                "description": f"自动优化第{shift + 1}班",
                "description_post": "",
                "Fiammetta": {"enable": fiammetta_enable, "target": current_target, "order": "pre"},  # 每个班次设置不同目标
                "rooms": {
                    "trading": [],
                    "manufacture": [],
                    "control": [{"operators": []}],  # 初始化为空
                    "power": [],
                    "meeting": [{"autofill": True}],
                    "hire": [{"operators": []}],
                    "dormitory": [{"autofill": True} for _ in range(4)],  # 初始化为自动填充
                    "processing": [{"operators": []}],
                }
            }
            # 班次内干员使用跟踪，防止同一班重复分配
            shift_used_names = set()
            # 班次内控制中枢干员集合（去重）
            control_operators = set()
            # 班次内宿舍干员集合（去重）
            dormitory_operators = set()

            # 优化贸易站
            for workplace in self.workplaces['trading_stations']:
                result = self.optimize_workplace(workplace, operator_usage, shift_used_names)
                room = {
                    "operators": [op.name for op in result.optimal_operators],
                    "autofill": False if result.optimal_operators else True,
                    "product": workplace.current_product  # 新增产物字段
                }
                plan["rooms"]["trading"].append(room)
                # 添加控制中枢需求干员
                for req in result.control_center_requirements:
                    if req.operator not in shift_used_names and operator_usage.get(req.operator, 0) < 2:
                        control_operators.add(req.operator)
                        shift_used_names.add(req.operator)
                        operator_usage[req.operator] += 1
                # 添加宿舍需求干员
                for req in result.dormitory_requirements:
                    if req.operator not in shift_used_names and operator_usage.get(req.operator, 0) < 2:
                        dormitory_operators.add(req.operator)
                        shift_used_names.add(req.operator)
                        operator_usage[req.operator] += 1

            # 优化制造站
            for workplace in self.workplaces['manufacturing_stations']:
                result = self.optimize_workplace(workplace, operator_usage, shift_used_names)
                room = {
                    "operators": [op.name for op in result.optimal_operators],
                    "autofill": False if result.optimal_operators else True,
                    "product": workplace.current_product  # 新增产物字段
                }
                plan["rooms"]["manufacture"].append(room)
                # 添加控制中枢需求干员
                for req in result.control_center_requirements:
                    if req.operator not in shift_used_names and operator_usage.get(req.operator, 0) < 2:
                        control_operators.add(req.operator)
                        shift_used_names.add(req.operator)
                        operator_usage[req.operator] += 1
                # 添加宿舍需求干员
                for req in result.dormitory_requirements:
                    if req.operator not in shift_used_names and operator_usage.get(req.operator, 0) < 2:
                        dormitory_operators.add(req.operator)
                        shift_used_names.add(req.operator)
                        operator_usage[req.operator] += 1

            # 分配控制中枢干员
            plan["rooms"]["control"][0]["operators"] = list(control_operators)

            # 分配宿舍干员（分配到第一个宿舍房间）
            if dormitory_operators:
                plan["rooms"]["dormitory"][0] = {
                    "operators": list(dormitory_operators),
                    "autofill": True
                }

            # 优化会客室
            result = self.optimize_workplace(self.workplaces['meeting_room'][0], operator_usage, shift_used_names)
            plan["rooms"]["meeting"][0] = {
                "operators": [op.name for op in result.optimal_operators],
                "autofill": False if result.optimal_operators else True
            }

            # 优化发电站
            for workplace in self.workplaces['power_station']:
                result = self.optimize_workplace(workplace, operator_usage, shift_used_names)
                plan["rooms"]["power"].append({
                    "operators": [op.name for op in result.optimal_operators],
                    "autofill": False if result.optimal_operators else True
                })

            results["plans"].append(plan)

        return results

    def select_fiammetta_targets(self) -> List[str]:
        """自动选择菲亚梅塔目标：优先巫恋、龙舌兰、但书，其余按贸易站效率排序，取前3个可用干员"""
        candidates = ['巫恋', '龙舌兰', '但书']
        selected = []
        for candidate in candidates:
            if candidate in self.operators and self.operators[candidate].own and self.operators[candidate].elite >= 2:
                selected.append(candidate)
                if len(selected) >= 3:
                    return selected

        # 如果不足3个，选择贸易站效率最高的干员（基于规则中的出现和效率）
        trading_rules = [r for r in self.efficiency_rules if r.workplace_type == 'trading_station']
        op_scores = {}
        for rule in trading_rules:
            for op in rule.operators:
                if op in self.operators and self.operators[op].own and self.operators[op].elite >= 2 and op not in selected:
                    score = rule.synergy_efficiency / len(rule.operators)  # 平均贡献
                    op_scores[op] = op_scores.get(op, 0) + score
        sorted_ops = sorted(op_scores, key=op_scores.get, reverse=True)
        for op in sorted_ops:
            selected.append(op)
            if len(selected) >= 3:
                break
        return selected

    def serialize_assignment_result(self, result: AssignmentResult) -> Dict[str, Any]:
        """序列化分配结果"""
        return {
            "workplace_id": result.workplace.id,
            "workplace_name": result.workplace.name,
            "optimal_operators": [
                {
                    "name": op.name,
                    "elite": op.elite,
                    "level": op.level
                }
                for op in result.optimal_operators
            ],
            "total_efficiency": round(result.total_efficiency, 1),
            "operator_efficiency": round(result.operator_efficiency, 1),
            "applied_combinations": result.applied_combinations,
            "control_center_requirements": [
                {
                    "operator": req.operator,
                    "elite_required": req.elite_required
                }
                for req in result.control_center_requirements
            ],
            "dormitory_requirements": [
                {
                    "operator": req.operator,
                    "elite_required": req.elite_required
                }
                for req in result.dormitory_requirements
            ]
        }

    def display_optimal_assignments(self):
        """显示最优分配方案（三班制）"""
        assignments = self.get_optimal_assignments()

        print("=== 最优工作站分配方案（三班制）===")
        print(f"标题: {assignments['title']}")
        print(f"描述: {assignments['description']}")
        print()

        for plan in assignments['plans']:
            print(f"班次: {plan['name']}")
            print(f"描述: {plan['description']}")
            fiammetta = plan.get('Fiammetta', {})
            if fiammetta.get('enable', False):
                print(f"菲亚梅塔: 启用，目标: {fiammetta.get('target', '无')}")
            else:
                print("菲亚梅塔: 未启用")
            print("房间分配:")
            for room_type, rooms in plan['rooms'].items():
                if room_type in ['trading', 'manufacture']:
                    name = {'trading': '贸易站', 'manufacture': '制造站'}
                    for i, room in enumerate(rooms):
                        product = room.get('product', '无')
                        operators = room.get('operators', [])
                        autofill = room.get('autofill', True)
                        print(f"  {name[room_type]} {i + 1}: 产物={product}, 干员={operators}, 自动填充={autofill}")
                elif room_type == 'power':
                    for i, room in enumerate(rooms):
                        operators = room.get('operators', [])
                        autofill = room.get('autofill', True)
                        print(f"  发电站 {i + 1}: 干员={operators}, 自动填充={autofill}")
                elif room_type == 'meeting':
                    room = rooms[0]
                    operators = room.get('operators', [])
                    autofill = room.get('autofill', True)
                    print(f"  会客室: 干员={operators}, 自动填充={autofill}")
                elif room_type == 'control':
                    operators = rooms[0].get('operators', [])
                    print(f"  控制中枢: 干员={operators}")
                elif room_type == 'dormitory':
                    for i, room in enumerate(rooms):
                        operators = room.get('operators', [])
                        autofill = room.get('autofill', True)
                        if operators or not autofill:
                            print(f"  宿舍 {i + 1}: 干员={operators}, 自动填充={autofill}")
            print()

    # 新增调试打印函数
    def print_loaded_files(self):
        print(f"DEBUG: 已加载的效率文件: {self.efficiency_file}")
        print(f"DEBUG: 已加载的干员文件: {self.operator_file}")

    def print_operator_summary(self):
        owned = [op for op in self.operators.values() if op.own]
        print(f"DEBUG: 干员总数: {len(self.operators)}，已拥有: {len(owned)}")
        if owned:
            sample = ', '.join([f"{op.name}(精{op.elite})" for op in owned[:20]])
            print(f"DEBUG: 已拥有干员示例（最多20）: {sample}")

    def print_efficiency_rules(self, limit: int = 10):
        print(f"DEBUG: 效率规则总数: {len(self.efficiency_rules)}，显示前 {limit} 项")
        for i, rule in enumerate(self.efficiency_rules[:limit]):
            cc = ','.join([f"{r.operator}(精{r.elite_required})" for r in rule.requires_control_center])
            print(f"  [{i+1}] {rule.description} | 类型: {rule.workplace_type} | 干员: {', '.join(rule.operators)} | 协同: {rule.synergy_efficiency}% | 中枢: {cc} | 精英要求: {rule.elite_requirements}")

    def print_workplaces(self):
        ts = self.workplaces.get('trading_stations', [])
        ms = self.workplaces.get('manufacturing_stations', [])
        print(f"DEBUG: 贸易站数量: {len(ts)}，制造站数量: {len(ms)}")
        for w in ts + ms:
            print(f"  - {w.id} {w.name} | 最大干员: {w.max_operators} | 基础效率: {w.base_efficiency}%")

# 使用示例
if __name__ == "__main__":
    optimizer = WorkplaceOptimizer('efficiency.json', 'operators.json', 'config.json', debug=False)
    optimizer.display_optimal_assignments()

    # 获取最优分配的JSON格式
    optimal_assignments = optimizer.get_optimal_assignments()

    # 保存最优分配结果
    with open('optimal_assignments.json', 'w', encoding='utf-8') as f:
        json.dump(optimal_assignments, f, ensure_ascii=False, indent=2)

    print("最优分配方案已保存到 optimal_assignments.json")