import itertools
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import symengine
import sympy

from pharmpy import Model
from pharmpy.data import ColumnType
from pharmpy.math import conditional_joint_normal, is_posdef
from pharmpy.parameter_sampling import sample_from_covariance_matrix, sample_individual_estimates
from pharmpy.random_variables import VariabilityLevel
from pharmpy.results import Results

# from typing import NamedTuple
# class FREMOptions(NamedTuple):
#    rescale: bool = True
#    uncertainty_method: str = 'cov_sampling'


class FREMResults(Results):
    def __init__(self, covariate_effects=None, individual_effects=None,
                 unexplained_variability=None, covariate_statistics=None,
                 covariate_effects_plot=None, individual_effects_plot=None,
                 covariate_baselines=None):
        # Lots of boilerplate code ahead. Could be simplified with python 3.7 dataclass
        self.covariate_effects = covariate_effects
        self.individual_effects = individual_effects
        self.unexplained_variability = unexplained_variability
        self.covariate_statistics = covariate_statistics
        self.covariate_effects_plot = covariate_effects_plot
        self.individual_effects_plot = individual_effects_plot
        self.covariate_baselines = covariate_baselines

    def to_dict(self):
        return {'covariate_effects': self.covariate_effects,
                'individual_effects': self.individual_effects,
                'unexplained_variability': self.unexplained_variability,
                'covariate_statistics': self.covariate_statistics,
                'covariate_effects_plot': self.covariate_effects_plot,
                'individual_effects_plot': self.individual_effects,
                'covariate_baselines': self.covariate_baselines}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def add_plots(self):
        self.covariate_effects_plot = self.plot_covariate_effects()
        self.individual_effects_plot = self.plot_individual_effects()

    def plot_covariate_effects(self):
        ce = (self.covariate_effects - 1) * 100
        cov_stats = pd.melt(self.covariate_statistics.reset_index(), var_name='condition',
                            id_vars=['covariate'], value_vars=['p5', 'p95'])

        cov_stats = cov_stats.replace({'p5': '5th', 'p95': '95th'}).set_index(['covariate',
                                                                               'condition'])
        ce = ce.join(cov_stats, how='inner')
        # The left join reorders the index. Might be pandas bug.
        ce = ce.reorder_levels(['parameter', 'covariate', 'condition'])

        param_names = list(ce.index.get_level_values('parameter').unique())
        plots = []

        for parameter in param_names:
            df = ce.xs(parameter, level=0)
            df = df.reset_index()

            error_bars = alt.Chart(df).mark_errorbar(ticks=True).encode(
                x=alt.X('p5:Q', title='Effect size in percent', scale=alt.Scale(zero=False)),
                x2=alt.X2('p95:Q'),
                y=alt.Y('condition:N', title=None),
            ).properties(width=400, height=100)

            rule = alt.Chart(df).mark_rule(strokeDash=[10, 4], color='gray').encode(
                x=alt.X('xzero:Q')
            ).transform_calculate(xzero="0")

            points = alt.Chart(df).mark_point(filled=True, color='black').encode(
                x=alt.X('mean:Q'),
                y=alt.Y('condition:N'),
            )

            text = alt.Chart(df).mark_text(
                dy=-15,
                color="red"
            ).encode(
                x=alt.X("mean:Q"),
                y=alt.Y("condition:N"),
                text=alt.Text("value:Q")
            )

            bar_values = alt.Chart(df).mark_text(
                dy=15,
            ).encode(
                x=alt.X("p5:Q"),
                y=alt.Y("condition:N"),
                text=alt.Text("p5:Q", format='.1f'),
            )

            plot = alt.layer(error_bars, bar_values, rule, points, text, data=df).facet(
                columns=1.0,
                row=alt.Facet('covariate:N', title=None),
                title=f'{parameter}'
            )

            plots.append(plot)

        v = alt.vconcat(*plots).resolve_scale(x='shared')
        return v

    def plot_individual_effects(self):
        covs = self.covariate_baselines
        ie = self.individual_effects.join(covs)
        param_names = list(ie.index.get_level_values('parameter').unique())
        ie = (ie - 1) * 100
        ie = ie.sort_values(by=['observed'])

        plots = []

        for parameter in param_names:
            df = ie.xs(parameter, level=1)

            id_order = list(df.index)
            id_order = [str(int(x)) for x in id_order]

            if len(df) > 20:
                id_order[10] = '...'

            df = df.reset_index()
            df['ID'] = df['ID'].astype(int).astype(str)

            error_bars = alt.Chart(df).mark_errorbar(ticks=True).encode(
                x=alt.X('p5:Q', title='Effect size in percent', scale=alt.Scale(zero=False)),
                x2=alt.X2('p95:Q'),
                y=alt.Y('ID:N', title='ID', sort=id_order),
                tooltip=['ID', 'p5', 'observed', 'p95'] + list(covs.columns),
            )

            rule = alt.Chart(df).mark_rule(strokeDash=[10, 2], color='gray').encode(
                x=alt.X('xzero:Q')
            ).transform_calculate(xzero="0")

            points = alt.Chart(df).mark_point(size=40, filled=True, color='black').encode(
                x=alt.X('observed:Q'),
                y=alt.Y('ID:N', sort=id_order),
            )

            plot = alt.layer(points, error_bars, rule, data=df,
                             title=f'Individuals for parameter {parameter}')
            if len(df) > 20:
                plot = plot.transform_window(
                        sort=[alt.SortField('observed', order='ascending')],
                        rank='row_number(observed)',
                    ).transform_window(
                         sort=[alt.SortField('observed', order='descending')],
                         nrank='row_number(observed)'
                    ).transform_filter(
                        'datum.rank <= 10 | datum.nrank <= 11'
                    ).transform_calculate(
                        ID="datum.nrank == 11 ? '...' : datum.ID",
                        p5="datum.nrank == 11 ? '...' : datum.p5",
                        p95="datum.nrank == 11 ? '...' : datum.p95",
                        observed="datum.nrank == 11 ? '...' : datum.observed",
                    )
            plots.append(plot)

        v = alt.vconcat(*plots).resolve_scale(x='shared')
        return v

    def __str__(self):
        start = f'Results from FREM'
        # method...
        # covs = f'Continuous covariates: {self.continuous}'
        # cats = f'Categorical covariates: {self.categorical}'
        # FIXME: General option object for this?
        # if self.rescale:
        #    resc = 'Rescaling was used'
        # else:
        #    resc = 'Rescaling was not used'
        ce = self.covariate_effects.to_string(index=False)
        ie = self.individual_effects.to_string()
        uv = self.unexplained_variability.to_string(index=False)
        cs = self.covariate_statistics.to_string()
        return f'{start}\n\nCovariate statistics\n{cs}\n\n' \
               f'Covariate effects\n{ce}\n\nIndividual effects\n{ie}\n\n' \
               f'Unexplained variability\n{uv}\n'


def calculate_results(frem_model, continuous, categorical, method=None, **kwargs):
    """Calculate FREM results

       :param method: Either 'cov_sampling' or 'bipp'
    """
    if method is None or method == 'cov_sampling':
        res = calculate_results_using_cov_sampling(frem_model, continuous, categorical, **kwargs)
    elif method == 'bipp':
        res = calculate_results_using_bipp(frem_model, continuous, categorical)
    else:
        raise ValueError(f'Unknown frem postprocessing method {method}')
    return res


def calculate_results_using_cov_sampling(frem_model, continuous, categorical, cov_model=None,
                                         force_posdef_samples=500, force_posdef_covmatrix=False,
                                         samples=1000, rescale=True):
    """Calculate the FREM results using covariance matrix for uncertainty

       :param cov_model: Take the parameter uncertainty covariance matrix from this model
                         instead of the frem model.
       :param force_posdef_samples: The number of sampling tries before stopping to use
                                    rejection sampling and instead starting to shift values so
                                    that the frem matrix becomes positive definite. Set to 0 to
                                    always force positive definiteness.
       :param force_posdef_covmatrix: Set to force the covariance matrix of the frem movdel or
                                      the cov model to be positive definite. Default is to raise
                                      in this case.
       :param samples: The number of parameter vector samples to use.
    """
    if cov_model is not None:
        uncertainty_results = cov_model.modelfit_results
    else:
        uncertainty_results = frem_model.modelfit_results

    _, dist = list(frem_model.random_variables.distributions(
        level=VariabilityLevel.IIV))[-1]
    sigma_symb = dist.sigma

    parameters = [s for s in frem_model.modelfit_results.parameter_estimates.index
                  if sympy.Symbol(s) in sigma_symb.free_symbols]
    parvecs = sample_from_covariance_matrix(frem_model,
                                            modelfit_results=uncertainty_results,
                                            force_posdef_samples=force_posdef_samples,
                                            force_posdef_covmatrix=force_posdef_covmatrix,
                                            parameters=parameters,
                                            n=samples)
    res = calculate_results_from_samples(frem_model, continuous, categorical, parvecs,
                                         rescale=rescale)
    return res


def calculate_results_from_samples(frem_model, continuous, categorical, parvecs, rescale=True):
    """Calculate the FREM results given samples of parameter estimates
    """
    n = len(parvecs)
    rvs, dist = list(frem_model.random_variables.distributions(
        level=VariabilityLevel.IIV))[-1]
    sigma_symb = dist.sigma
    parameters = [s for s in frem_model.modelfit_results.parameter_estimates.index
                  if sympy.Symbol(s) in sigma_symb.free_symbols]
    parvecs = parvecs.append(
            frem_model.modelfit_results.parameter_estimates.loc[parameters])

    df = frem_model.input.dataset
    covariates = continuous + categorical
    df.pharmpy.column_type[covariates] = ColumnType.COVARIATE
    covariate_baselines = df.pharmpy.covariate_baselines
    covariate_baselines = covariate_baselines[covariates]
    cov_means = covariate_baselines.mean()
    cov_modes = covariate_baselines.mode().iloc[0]      # Select first mode if more than one
    cov_others = pd.Series(index=cov_modes[categorical].index, dtype=np.float64)
    cov_stdevs = covariate_baselines.std()
    for _, row in covariate_baselines.iterrows():
        for cov in categorical:
            if row[cov] != cov_modes[cov]:
                cov_others[cov] = row[cov]
        if not cov_others.isna().values.any():
            break

    cov_refs = pd.concat((cov_means[continuous], cov_modes[categorical]))
    cov_5th = covariate_baselines.quantile(0.05, interpolation='lower')
    cov_95th = covariate_baselines.quantile(0.95, interpolation='higher')
    is_categorical = cov_refs.index.isin(categorical)

    res = FREMResults()

    res.covariate_statistics = pd.DataFrame({'p5': cov_5th, 'mean': cov_means,
                                             'p95': cov_95th, 'stdev': cov_stdevs,
                                             'ref': cov_refs, 'categorical': is_categorical,
                                             'other': cov_others}, index=covariates)
    res.covariate_statistics.index.name = 'covariate'

    ncovs = len(covariates)
    npars = sigma_symb.rows - ncovs
    nids = len(covariate_baselines)
    param_indices = list(range(npars))
    if rescale:
        scaling = np.diag(np.concatenate((np.ones(npars), cov_stdevs.values)))

    mu_bars_given_5th = np.empty((n, ncovs, npars))
    mu_bars_given_95th = np.empty((n, ncovs, npars))
    mu_id_bars = np.empty((n, nids, npars))
    original_id_bar = np.empty((nids, npars))
    variability = np.empty((n, ncovs + 2, npars))      # none, cov1, cov2, ..., all
    original_variability = np.empty((ncovs + 2, npars))

    # Switch to symengine for speed
    # Could also assume order of parameters, but not much gain
    sigma_symb = symengine.sympify(sigma_symb)
    parvecs.columns = [symengine.Symbol(colname) for colname in parvecs.columns]

    covbase = covariate_baselines.to_numpy()

    for sample_no, params in parvecs.iterrows():
        sigma = sigma_symb.subs(dict(params))
        sigma = np.array(sigma).astype(np.float64)
        if rescale:
            sigma = scaling @ sigma @ scaling
        if sample_no != 'estimates':
            variability[sample_no, 0, :] = np.diag(sigma)[:npars]
        else:
            original_variability[0, :] = np.diag(sigma)[:npars]
        for i, cov in enumerate(covariates):
            indices = param_indices + [i + npars]
            cov_sigma = sigma[indices][:, indices]
            cov_mu = np.array([0] * npars + [cov_refs[cov]])
            if cov in categorical:
                first_reference = cov_others[cov]
            else:
                first_reference = cov_5th[cov]
            mu_bar_given_5th_cov, sigma_bar = conditional_joint_normal(
                cov_mu, cov_sigma, np.array([first_reference]))
            if sample_no != 'estimates':
                mu_bar_given_95th_cov, _ = conditional_joint_normal(cov_mu, cov_sigma,
                                                                    np.array([cov_95th[cov]]))
                mu_bars_given_5th[sample_no, i, :] = mu_bar_given_5th_cov
                mu_bars_given_95th[sample_no, i, :] = mu_bar_given_95th_cov
                variability[sample_no, i + 1, :] = np.diag(sigma_bar)
            else:
                original_variability[i + 1, :] = np.diag(sigma_bar)

        for i in range(len(covariate_baselines)):
            row = covbase[i, :]
            id_mu = np.array([0] * npars + list(cov_refs))
            mu_id_bar, sigma_id_bar = conditional_joint_normal(id_mu, sigma, row)
            if sample_no != 'estimates':
                mu_id_bars[sample_no, i, :] = mu_id_bar
                variability[sample_no, -1, :] = np.diag(sigma_id_bar)
            else:
                original_id_bar[i, :] = mu_id_bar
                original_variability[ncovs + 1, :] = np.diag(sigma_id_bar)

    # Create covariate effects table
    mu_bars_given_5th = np.exp(mu_bars_given_5th)
    mu_bars_given_95th = np.exp(mu_bars_given_95th)

    means_5th = np.mean(mu_bars_given_5th, axis=0)
    means_95th = np.mean(mu_bars_given_95th, axis=0)
    q5_5th = np.quantile(mu_bars_given_5th, 0.05, axis=0)
    q5_95th = np.quantile(mu_bars_given_95th, 0.05, axis=0)
    q95_5th = np.quantile(mu_bars_given_5th, 0.95, axis=0)
    q95_95th = np.quantile(mu_bars_given_95th, 0.95, axis=0)

    df = pd.DataFrame(columns=['parameter', 'covariate', 'condition', 'p5', 'mean', 'p95'])
    param_names = [rv.name for rv in rvs][:npars]
    for param, cov in itertools.product(range(npars), range(ncovs)):
        if covariates[cov] in categorical:
            df = df.append({'parameter': param_names[param], 'covariate': covariates[cov],
                            'condition': 'other', 'p5': q5_5th[cov, param],
                            'mean': means_5th[cov, param], 'p95': q95_5th[cov, param]},
                           ignore_index=True)
        else:
            df = df.append({'parameter': param_names[param], 'covariate': covariates[cov],
                            'condition': '5th', 'p5': q5_5th[cov, param],
                            'mean': means_5th[cov, param], 'p95': q95_5th[cov, param]},
                           ignore_index=True)
            df = df.append({'parameter': param_names[param], 'covariate': covariates[cov],
                            'condition': '95th', 'p5': q5_95th[cov, param],
                            'mean': means_95th[cov, param], 'p95': q95_95th[cov, param]},
                           ignore_index=True)
    df.set_index(['parameter', 'covariate', 'condition'], inplace=True)
    res.covariate_effects = df

    # Create id table
    mu_id_bars = np.exp(mu_id_bars)
    original_id_bar = np.exp(original_id_bar)

    with np.testing.suppress_warnings() as sup:     # Would warn in case of missing covariates
        sup.filter(RuntimeWarning, "All-NaN slice encountered")
        id_5th = np.nanquantile(mu_id_bars, 0.05, axis=0)
        id_95th = np.nanquantile(mu_id_bars, 0.95, axis=0)

    df = pd.DataFrame(columns=['parameter', 'observed', 'p5', 'p95'])
    for curid, param in itertools.product(range(nids), range(npars)):
        df = df.append(pd.Series({'parameter': param_names[param],
                                  'observed': original_id_bar[curid, param],
                                  'p5': id_5th[curid, param],
                                  'p95': id_95th[curid, param]},
                                 name=covariate_baselines.index[curid]))
    df.index.name = 'ID'
    df = df.set_index('parameter', append=True)
    res.individual_effects = df

    # Create unexplained variability table
    sd_5th = np.sqrt(np.nanquantile(variability, 0.05, axis=0))
    sd_95th = np.sqrt(np.nanquantile(variability, 0.95, axis=0))
    original_sd = np.sqrt(original_variability)

    df = pd.DataFrame(columns=['parameter', 'covariate', 'sd_observed', 'sd_5th', 'sd_95th'])
    for par, cond in itertools.product(range(npars), range(ncovs + 2)):
        if cond == 0:
            condition = 'none'
        elif cond == ncovs + 1:
            condition = 'all'
        else:
            condition = covariates[cond - 1]
        df = df.append({'parameter': param_names[par], 'covariate': condition,
                        'sd_observed': original_sd[cond, par], 'sd_5th': sd_5th[cond, par],
                        'sd_95th': sd_95th[cond, par]}, ignore_index=True)
    df = df.set_index(['parameter', 'covariate'])
    res.unexplained_variability = df

    res.covariate_baselines = covariate_baselines

    return res


def calculate_results_using_bipp(frem_model, continuous, categorical, rescale=True, samples=2000):
    """Estimate a covariance matrix for the frem model using the BIPP method

        Bootstrap on the individual parameter posteriors
       Only the individual estimates, individual unvertainties and the parameter estimates
       are needed.
    """
    rvs, dist = list(frem_model.random_variables.distributions(
        level=VariabilityLevel.IIV))[-1]
    etas = [rv.name for rv in rvs]
    pool = sample_individual_estimates(frem_model, parameters=etas)
    ninds = len(pool.index.unique())
    ishr = frem_model.modelfit_results.individual_shrinkage
    lower_indices = np.tril_indices(len(etas))
    pop_params = np.array(dist.sigma).astype(str)[lower_indices]
    parameter_samples = np.empty((samples, len(pop_params)))
    remaining_samples = samples
    k = 0
    while k < remaining_samples:
        bootstrap = pool.sample(n=ninds, replace=True)
        ishk = ishr.loc[bootstrap.index]
        cf = (1 / (1 - ishk.mean())) ** (1/2)
        corrected_bootstrap = bootstrap * cf
        bootstrap_cov = corrected_bootstrap.cov()
        if not is_posdef(bootstrap_cov.to_numpy()):
            continue
        parameter_samples[k, :] = bootstrap_cov.values[lower_indices]
        k += 1
    frame = pd.DataFrame(parameter_samples, columns=pop_params)
    res = calculate_results_from_samples(frem_model, continuous, categorical, frame,
                                         rescale=rescale)
    return res


def psn_frem_results(path, force_posdef_covmatrix=False, method=None):
    """ Create frem results from a PsN FREM run

        :param path: Path to PsN frem run directory
        :return: A :class:`FREMResults` object
    """
    path = Path(path)

    model_4_path = path / 'final_models' / 'model_4.mod'
    if not model_4_path.is_file():
        raise IOError(f'Could not find FREM model 4: {str(model_4_path)}')
    model_4 = Model(model_4_path)
    if model_4.modelfit_results is None:
        raise ValueError('Model 4 has no results')
    try:
        model_4.modelfit_results.covariance_matrix
    except Exception:
        model_4b_path = path / 'final_models' / 'model_4b.mod'
        model_4b = Model(model_4b_path)
        cov_model = model_4b
    else:
        cov_model = None

    with open(path / 'covariates_summary.csv') as covsum:
        covsum.readline()
        raw_cov_list = covsum.readline()

    all_covariates = raw_cov_list[1:].rstrip().split(',')
    nunique = model_4.input.dataset[all_covariates].nunique()
    continuous = list(nunique.index[nunique != 2])
    categorical = list(nunique.index[nunique == 2])

    res = calculate_results(model_4, continuous, categorical, method=method,
                            force_posdef_covmatrix=force_posdef_covmatrix, cov_model=cov_model)
    return res
