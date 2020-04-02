import itertools

import numpy as np
import pandas as pd

from pharmpy.data import ColumnType
from pharmpy.math import conditional_joint_normal
from pharmpy.parameter_sampling import sample_from_covariance_matrix
from pharmpy.random_variables import VariabilityLevel
from pharmpy.results import Results


class FREMResults(Results):
    def __init__(self, frem_model, cov_model=None, continuous=[], categorical=[], samples=1000):
        covariates = continuous + categorical
        self.frem_model = frem_model
        n = samples

        if cov_model is not None:
            cov_results = cov_model.modelfit_results
        else:
            cov_results = frem_model.modelfit_results

        parvecs = sample_from_covariance_matrix(frem_model, modelfit_results=cov_results, n=n)
        parvecs = parvecs.append(frem_model.modelfit_results.parameter_estimates)

        _, dist = list(frem_model.random_variables.distributions(level=VariabilityLevel.IIV))[-1]
        sigma_symb = dist.sigma

        df = frem_model.input.dataset
        df.pharmpy.column_type[covariates] = ColumnType.COVARIATE
        covariate_baselines = df.pharmpy.covariate_baselines
        covariate_baselines = covariate_baselines[covariates]
        cov_stdevs = covariate_baselines.std()
        cov_means = covariate_baselines.mean()
        cov_modes = covariate_baselines.mode().iloc[0]      # Select first mode if more than one
        cov_others = pd.Series(index=cov_modes[categorical].index, dtype=np.float64)
        for _, row in covariate_baselines.iterrows():
            for cov in categorical:
                if row[cov] != cov_modes[cov]:
                    cov_others[cov] = row[cov]
            if not cov_others.isna().values.any():
                break

        cov_refs = pd.concat((cov_means[continuous], cov_modes[categorical]))
        cov_5th = covariate_baselines.quantile(0.05, interpolation='lower')
        cov_95th = covariate_baselines.quantile(0.95, interpolation='higher')

        self.covariate_statistics = pd.DataFrame({'5th': cov_5th, 'ref': cov_refs,
                                                  '95th': cov_95th})

        ncovs = len(covariates)
        npars = sigma_symb.rows - ncovs
        nids = len(covariate_baselines)
        param_indices = list(range(npars))
        scaling = np.diag(np.concatenate((np.ones(npars), cov_stdevs.values)))

        mu_bars_given_5th = np.empty((n, ncovs, npars))
        mu_bars_given_95th = np.empty((n, ncovs, npars))
        mu_id_bars = np.empty((n, nids, npars))
        original_id_bar = np.empty((nids, npars))
        variability = np.empty((n, ncovs + 2, npars))      # none, cov1, cov2, ..., all
        original_variability = np.empty((ncovs + 2, npars))

        for sample_no, params in parvecs.iterrows():
            sigma = sigma_symb.subs(dict(params))
            sigma = np.array(sigma).astype(np.float64)
            scaled_sigma = scaling @ sigma @ scaling.T
            if sample_no != 'estimates':
                variability[sample_no, 0, :] = np.diag(scaled_sigma)[:npars]
            else:
                original_variability[0, :] = np.diag(scaled_sigma)[:npars]
            for i, cov in enumerate(covariates):
                indices = param_indices + [i + npars]
                cov_sigma = scaled_sigma[indices][:, indices]
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

            for i, (_, row) in enumerate(covariate_baselines.iterrows()):
                id_mu = np.array([0] * npars + list(cov_refs))
                mu_id_bar, sigma_id_bar = conditional_joint_normal(id_mu, scaled_sigma, row.values)
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

        df = pd.DataFrame(columns=['parameter', 'covariate', 'condition', '5th', 'mean', '95th'])
        for param, cov in itertools.product(range(npars), range(ncovs)):
            if covariates[cov] in categorical:
                df = df.append({'parameter': str(param), 'covariate': covariates[cov],
                                'condition': 'other', '5th': q5_5th[cov, param],
                                'mean': means_5th[cov, param], '95th': q95_5th[cov, param]},
                               ignore_index=True)
            else:
                df = df.append({'parameter': str(param), 'covariate': covariates[cov],
                                'condition': '5th', '5th': q5_5th[cov, param],
                                'mean': means_5th[cov, param], '95th': q95_5th[cov, param]},
                               ignore_index=True)
                df = df.append({'parameter': str(param), 'covariate': covariates[cov],
                                'condition': '95th', '5th': q5_95th[cov, param],
                                'mean': means_95th[cov, param], '95th': q95_95th[cov, param]},
                               ignore_index=True)
        self.covariate_effects = df

        # Create id table
        mu_id_bars = np.exp(mu_id_bars)
        original_id_bar = np.exp(original_id_bar)

        id_5th = np.quantile(mu_id_bars, 0.05, axis=0)
        id_95th = np.quantile(mu_id_bars, 0.95, axis=0)

        df = pd.DataFrame(columns=['parameter', 'observed', '5th', '95th'])
        for curid, param in itertools.product(range(nids), range(npars)):
            df = df.append(pd.Series({'parameter': str(param),
                                      'observed': original_id_bar[curid, param],
                                      '5th': id_5th[curid, param],
                                      '95th': id_95th[curid, param]},
                                     name=covariate_baselines.index[curid]))
        self.individual_effects = df

        # Create unexplained variability table
        sd_5th = np.sqrt(np.quantile(variability, 0.05, axis=0))
        sd_95th = np.sqrt(np.quantile(variability, 0.95, axis=0))
        original_sd = np.sqrt(original_variability)

        df = pd.DataFrame(columns=['parameter', 'condition', 'sd_observed', 'sd_5th', 'sd_95th'])
        for par, cond in itertools.product(range(npars), range(ncovs + 2)):
            if cond == 0:
                condition = 'none'
            elif cond == ncovs + 1:
                condition = 'all'
            else:
                condition = covariates[cond - 1]
            df = df.append({'parameter': str(par), 'condition': condition,
                            'sd_observed': original_sd[cond, par], 'sd_5th': sd_5th[cond, par],
                            'sd_95th': sd_95th[cond, par]}, ignore_index=True)
        self.unexplained_variability = df