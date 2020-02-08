# Classes for method results

import pandas as pd

import pharmpy.visualization
from pharmpy.data import PharmDataFrame


class ModelfitResults:
    """ Results from a modelfit operation

    properties: individual_OFV is a df with currently ID and iOFV columns
        model_name - name of model that generated the results
    """
    @property
    def ofv(self):
        """Final objective function value
        """
        raise NotImplementedError("Not implemented")

    @property
    def parameter_estimates(self):
        """Parameter estimates as series
        """
        raise NotImplementedError("Not implemented")

    @property
    def covariance_matrix(self):
        """The covariance matrix of the population parameter estimates
        """
        raise NotImplementedError("Not implemented")

    @property
    def information_matrix(self):
        """The Fischer information matrix of the population parameter estimates
        """
        raise NotImplementedError("Not implemented")

    @property
    def individual_OFV(self):
        """A Series with individual estimates indexed over ID
        """
        raise NotImplementedError("Not implemented")

    def plot_iofv_vs_iofv(self, other):
        x_label = f'{self.model_name} iOFV'
        y_label = f'{other.model_name} iOFV'
        df = PharmDataFrame({x_label: self.individual_OFV, y_label: other.individual_OFV})
        plot = pharmpy.visualization.scatter_plot_correlation(df, x_label, y_label,
                                                              title='iOFV vs iOFV')
        return plot


class ChainedModelfitResults(list, ModelfitResults):
    """A list of modelfit results given in order from first to final
       inherits from both list and ModelfitResults. Each method from ModelfitResults
       will be performed on the final modelfit object
    """
    @property
    def ofv(self):
        return self[-1].ofv

    @property
    def parameter_estimates(self):
        return self[-1].parameter_estimates

    @property
    def covariance_matrix(self):
        return self[-1].covariance_matrix

    @property
    def information_matrix(self):
        return self[-1].information_matrix

    @property
    def individual_OFV(self):
        return self[-1].individual_OFV

    def plot_iOFV_vs_iOFV(self, other):
        return self[-1].plot_iOFV_vs_iOFV(other)

    @property
    def model_name(self):
        return self[-1].model_name

    # FIXME: To not have to manually intercept everything here. Should do it in a general way.


class CaseDeletionResults:
    def __init__(self, original_fit, case_deleted_fits):
        # Would also need group numbers. For dOFV can only do ID as group
        pass

    @property
    def cook_scores(self):
        """ Calculate a series of cook scores. One for each group
        """
        pass


class BootstrapResults:
    # FIXME: Could inherit from results that take multiple runs like bootstrap, cdd etc.
    def __init__(self, original_model, bootstrap_models):
        self._original_results = original_model.modelfit_results
        self._bootstrap_results = [m.modelfit_results for m in bootstrap_models]

    @property
    def ofv(self):
        boot_ofvs = [x.ofv for x in self._bootstrap_results]
        return pd.Series(boot_ofvs, name='ofv')

    @property
    def parameter_estimates(self):
        df = pd.DataFrame()
        for res in self._bootstrap_results:
            df = df.append(res.parameter_estimates, sort=False)
        df = df.reindex(self._bootstrap_results[0].parameter_estimates.index, axis=1)
        df = df.reset_index(drop=True)
        return df

    @property
    def standard_errors(self):
        pass
        # FIXME: Continue here

    @property
    def statistics(self):
        df = self.parameter_estimates
        ofvs = self.ofv
        df.insert(0, 'OFV', ofvs)
        orig = self._original_results.parameter_estimates
        ofv_ser = pd.Series({'OFV': self._original_results.ofv})
        orig = pd.concat([ofv_ser, orig])
        mean = df.mean()
        bias = mean - orig
        summary = pd.DataFrame({'mean': mean, 'bias': bias, 'stderr': df.std()})
        return summary

    @property
    def distribution(self):
        df = self.parameter_estimates
        ofvs = self.ofv
        df.insert(0, 'OFV', ofvs)
        summary = pd.DataFrame({'min': df.min(), '0.05%': df.quantile(0.0005),
                                '0.5%': df.quantile(0.005), '2.5%': df.quantile(0.025),
                                '5%': df.quantile(0.05), 'median': df.median(),
                                '95%': df.quantile(0.95), '97.5%': df.quantile(0.975),
                                '99.5%': df.quantile(0.995), '99.95%': df.quantile(0.9995),
                                'max': df.max()})
        return summary

    def __repr__(self):
        statistics = f'Statistics\n{repr(self.statistics)}'
        distribution = f'Distribution\n{repr(self.distribution)}'
        return f'{statistics}\n\n{distribution}'

    def plot_ofv(self):
        plot = pharmpy.visualization.histogram(self.ofv, title='Bootstrap OFV')
        return plot