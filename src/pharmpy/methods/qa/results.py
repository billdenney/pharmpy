from pathlib import Path

import numpy as np
import pandas as pd

import pharmpy.random_variables
import pharmpy.symbols
from pharmpy import Model
from pharmpy.random_variables import VariabilityLevel
from pharmpy.results import Results


class QAResults(Results):
    def __init__(
        self, dofv=None, fullblock_parameters=None, boxcox_parameters=None, tdist_parameters=None
    ):
        self.dofv = dofv
        self.fullblock_parameters = fullblock_parameters
        self.boxcox_parameters = boxcox_parameters
        self.tdist_parameters = tdist_parameters


def calculate_results(original_model, fullblock_model=None, boxcox_model=None, tdist_model=None):
    fullblock_table, fullblock_dofv = calc_fullblock(original_model, fullblock_model)
    boxcox_table, boxcox_dofv = calc_transformed_etas(
        original_model, boxcox_model, 'boxcox', 'lambda'
    )
    tdist_table, tdist_dofv = calc_transformed_etas(original_model, tdist_model, 'tdist', 'df')
    dofv_table = pd.concat([fullblock_dofv, boxcox_dofv, tdist_dofv])
    res = QAResults(
        dofv=dofv_table,
        fullblock_parameters=fullblock_table,
        boxcox_parameters=boxcox_table,
        tdist_parameters=tdist_table,
    )
    return res


def calc_transformed_etas(original_model, new_model, transform_name, parameter_name):
    """Retrieve new and old parameters of boxcox"""
    dofv_tab = pd.DataFrame({'dofv': np.nan, 'df': np.nan}, index=[transform_name])
    if new_model is None:
        return None, dofv_tab
    origres = original_model.modelfit_results
    newres = new_model.modelfit_results
    if newres is None:
        return None, dofv_tab
    params = new_model.random_variables.variance_parameters(exclude_level=VariabilityLevel.RUV)
    params = [pharmpy.symbols.symbol(p.name) for p in params]
    origres.reparameterize(
        [
            pharmpy.random_variables.NormalParametrizationSd,
            pharmpy.random_variables.MultivariateNormalParametrizationSdCorr,
        ]
    )
    newres.reparameterize(
        [
            pharmpy.random_variables.NormalParametrizationSd,
            pharmpy.random_variables.MultivariateNormalParametrizationSdCorr,
        ]
    )
    boxcox_sds = [newres.parameter_estimates[p.name] for p in params]
    orig_sds = [origres.parameter_estimates[p.name] for p in params]
    thetas = newres.parameter_estimates[0 : len(params)]
    eta_names = [rv.name for rv in new_model.random_variables.etas]

    table = pd.DataFrame(
        {parameter_name: thetas.values, 'new_sd': boxcox_sds, 'old_sd': orig_sds}, index=eta_names
    )

    dofv = origres.ofv - newres.ofv
    dofv_tab = pd.DataFrame({'dofv': dofv, 'df': len(eta_names)}, index=[transform_name])
    return table, dofv_tab


def calc_fullblock(original_model, fullblock_model):
    """Retrieve new and old parameters of full block"""
    dofv_tab = pd.DataFrame({'dofv': np.nan, 'df': np.nan}, index=['fullblock'])
    if fullblock_model is None:
        return None, dofv_tab
    origres = original_model.modelfit_results
    fullres = fullblock_model.modelfit_results
    if fullres is None:
        return None, dofv_tab
    _, dist = list(fullblock_model.random_variables.distributions(level=VariabilityLevel.IIV))[0]
    fullblock_parameters = [str(symb) for symb in dist.free_symbols]
    origres.reparameterize(
        [
            pharmpy.random_variables.NormalParametrizationSd,
            pharmpy.random_variables.MultivariateNormalParametrizationSdCorr,
        ]
    )
    fullres.reparameterize(
        [
            pharmpy.random_variables.NormalParametrizationSd,
            pharmpy.random_variables.MultivariateNormalParametrizationSdCorr,
        ]
    )
    new_params = (
        fullres.parameter_estimates[fullblock_parameters]
        .reindex(index=fullres.parameter_estimates.index)
        .dropna()
    )
    old_params = origres.parameter_estimates
    table = pd.DataFrame({'new': new_params, 'old': old_params}).reindex(index=new_params.index)

    degrees = table['old'].isna().sum()
    dofv = origres.ofv - fullres.ofv
    dofv_tab = pd.DataFrame({'dofv': dofv, 'df': degrees}, index=['fullblock'])
    return table, dofv_tab


def psn_qa_results(path):
    """Create qa results from a PsN qa run

    :param path: Path to PsN qa run directory
    :return: A :class:`QAResults` object
    """
    path = Path(path)

    original_model = Model(path / 'linearize_run' / 'scm_dir1' / 'derivatives.mod')
    fullblock_path = path / 'modelfit_run' / 'fullblock.mod'
    if fullblock_path.is_file():
        fullblock_model = Model(fullblock_path)
    else:
        fullblock_model = None
    boxcox_path = path / 'modelfit_run' / 'boxcox.mod'
    if boxcox_path.is_file():
        boxcox_model = Model(boxcox_path)
    else:
        boxcox_model = None
    tdist_path = path / 'modelfit_run' / 'tdist.mod'
    if tdist_path.is_file():
        tdist_model = Model(tdist_path)
    else:
        tdist_model = None

    res = calculate_results(
        original_model,
        fullblock_model=fullblock_model,
        boxcox_model=boxcox_model,
        tdist_model=tdist_model,
    )
    return res