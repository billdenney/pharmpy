"""
data.iterators
==============

Iterators generating new datasets from a dataset

Currenly contains:

1. Omit - Can be used for cdd
2. Resample - Can be used by bootstrap
"""
import collections
import numpy as np
import pandas as pd
from pathlib import Path

import pharmpy.math


class DatasetIterator:
    """ Base class for iterator classes that generate new datasets from an input dataset

        The __next__ function could return either a DataFrame or a tuple where the first
        element is the main DataFrame.
    """
    def __iter__(self):
        return self

    def data_files(self, path, filename="dataset_{}.dta"):
        """ Write all datasets to files

            All datasets of the iterator will be generated and written as csv files.

            :param Path path: Where to create the dataset files
            :param Format filename: A format string with one slot for the number of the
                resample starting from 1
            :return: A list of paths for all generated files
        """
        path = Path(path)
        self.paths = []
        for i, df in enumerate(self, 1):
            next_path = path / filename.format(i)
            if isinstance(df, tuple):
                df = df[0]
            df.to_csv(next_path)
            self.paths.append(next_path)

        return self.paths


class Omit(DatasetIterator):
    """ Iterate over omissions of a certain group in a dataset. One group is omitted at a time.

        :param DataFrame df: DataFrame to iterate over
        :param colname group: Name of the column to use for grouping
        :returns: Tuple of DataFrame and the omitted group
    """
    def __init__(self, df, group):
        self._unique_groups = df[group].unique()
        if len(self._unique_groups == 1):
            raise ValueError("Cannot create an Omit iterator as the number of unique groups is 1.")
        self._df = df
        self._counter = 0
        self._group = group

    def __next__(self):
        if self._counter == len(self._unique_groups):
            raise StopIteration
        df = self._df
        next_group = self._unique_groups[self._counter]
        new_df = df[df[self._group] != next_group]
        self._counter += 1
        return new_df, next_group

    def data_files(self, path, filename="omitted_{}.dta"):
        return super().data_files(path, filename)


class Resample(DatasetIterator):
    """ Iterate over resamples of a dataset.

        The dataset will be grouped on the group column then groups will be selected
        randomly with or without replacement to form a new dataset.
        The groups will be renumbered from 1 and upwards to keep them separated in the new
        dataset.

        Stratification will make sure that

        :param DataFrame df: DataFrame to iterate over
        :param colname group: Name of column to group by
        :param Int resamples: Number of resamples (iterations) to make
        :param colname stratify: Name of column to use for stratification.
            The values in the stratification column must be equal within a group so that the group
            can be uniquely determined. A ValueError exception will be raised otherwise.
        :param Int sample_size: The number of groups that should be sampled. The default is
            the number of groups. If using stratification the default is to sample using the
            proportion of the stratas in the dataset. A dictionary of specific sample sizes
            for each strata can also be supplied.
        :param bool replace: A boolean controlling whether sampling should be done with or
            without replacement

        :returns: A tuple of a resampled DataFrame and a list of resampled groups in order
    """

    def __init__(self, df, group, resamples=1, stratify=None, sample_size=None, replace=False):
        unique_groups = df[group].unique()
        numgroups = len(unique_groups)

        if sample_size is None:
            sample_size = numgroups

        if stratify:
            # Default is to use proportions in dataset
            stratas = df.groupby(stratify)[group].unique()
            have_mult_sample_sizes = isinstance(sample_size, collections.Mapping)
            if not have_mult_sample_sizes:
                non_rounded_sample_sizes = stratas.apply(lambda x: (len(x) / numgroups) * sample_size)
                rounded_sample_sizes = pharmpy.math.round_and_keep_sum(non_rounded_sample_sizes, sample_size)
                sample_size_dict = dict(rounded_sample_sizes)    # strata: numsamples
            else:
                sample_size_dict = sample_size

            stratas = dict(stratas)     # strata: list of groups
        else:
            sample_size_dict = {1: sample_size}
            stratas = {1: unique_groups}

        # Check that we will not run out of samples without replacement.
        if not replace:
            for strata in sample_size_dict:
                if sample_size_dict[strata] > len(stratas[strata]):
                    if stratify:
                        raise ValueError(
                            'The sample size ({sample_size}) for strata {strata} is larger than the number of groups'
                            ' ({numgroups}) in that strata which is impoosible with replacement.'.format(
                                sample_size=sample_size_dict[strata], strata=strata, numgroups=len(stratas[strata])))
                    else:
                        raise ValueError(
                            'The sample size ({sample_size}) is larger than the number of groups'
                            '({numgroups}) which is impossible with replacement.'.format(
                                sample_size=sample_size_dict[strata], numgroups=len(stratas[strata])))

        self._df = df
        self._group = group
        self._replace = replace
        self._stratas = stratas
        self._sample_size_dict = sample_size_dict
        self._resamples = resamples

    def __next__(self):
        if self._resamples == 0:
            raise StopIteration

        self._resamples -= 1
        random_groups = []
        for strata in self._sample_size_dict:
            random_groups += np.random.choice(self._stratas[strata], size=self._sample_size_dict[strata], replace=self._replace).tolist()

        new_df = pd.DataFrame()
        # Build the dataset given the random_groups list
        for grp_id, new_grp in zip(random_groups, range(1, len(random_groups) + 1)):
            sub = self._df.loc[self._df[self._group] == grp_id].copy()
            sub[self._group] = new_grp
            new_df = new_df.append(sub)
        new_df.reset_index(inplace=True, drop=True)

        return new_df, random_groups

    def data_files(self, path, filename="resample_{}.dta"):
        return super().data_files(path, filename)