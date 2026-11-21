"""One explicitly configured entry point for small reproducible fixtures."""
from .world import make_episode
from .payment_world import make_payment_episode
from .fx_world import make_fx_episode
from .period_world import make_period_episode
from .compound_world import make_fx_allocation, make_duplicate_allocation


def generate_episode(seed, config):
    if type(seed) is not int or not isinstance(config, dict):
        raise ValueError('invalid seed or config')
    scenario = config.get('scenario')
    if not isinstance(scenario, str):
        raise ValueError('invalid scenario')
    if scenario == 'company_settlements':
        from .company_world_v2 import build_settlement_company
        return build_settlement_company(seed, {key: value for key, value in config.items() if key != 'scenario'})[:2]
    if scenario == 'company_settlement_fault':
        from .settlement_faults_v2 import build_settlement_fault_episode
        return build_settlement_fault_episode(
            seed, {key: value for key, value in config.items() if key != 'scenario'})[:2]
    if scenario == 'company':
        from .company_world import build_company
        return build_company(seed, {key: value for key, value in config.items() if key != 'scenario'})[:2]
    single = {'duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period'}
    compound = {'fx_allocation', 'duplicate_allocation'}
    if scenario in single:
        if set(config) - {'scenario', 'fault'} or type(config.get('fault', True)) is not bool:
            raise ValueError('invalid scenario config')
        fault = config.get('fault', True)
        if scenario == 'duplicate_invoice':
            return make_episode(seed, fault)
        if scenario == 'payment_allocation':
            return make_payment_episode(seed, 'partial' if fault else 'none')
        if scenario == 'fx_rate_or_date':
            return make_fx_episode(seed, 'wrong_date' if fault else 'none')
        return make_period_episode(seed, fault)
    if scenario in compound:
        if set(config) - {'scenario', 'first_fault', 'allocation_fault'} or type(config.get('first_fault', True)) is not bool or type(config.get('allocation_fault', True)) is not bool:
            raise ValueError('invalid compound config')
        first, allocation = config.get('first_fault', True), config.get('allocation_fault', True)
        return (make_fx_allocation if scenario == 'fx_allocation' else make_duplicate_allocation)(seed, first, allocation)
    raise ValueError('unknown scenario')
