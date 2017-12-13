import os
import numpy as np
from textwrap import TextWrapper
from copy import deepcopy

def find_keyword(arr_line, keyword_dict):
    # convert to lower case
    arr_line_lower = []
    for word in arr_line:
        # integers and floats are not keywords
        if not DatumUtil.is_int(word) and not DatumUtil.is_float(word):
            arr_line_lower.append(word.lower())
    # look for constants in order of most words to least words
    key = ''
    for num_words in range(len(arr_line_lower), -1, -1):
        key = tuple(arr_line_lower[0:num_words])
        if len(key) > 0 and key in keyword_dict:
            return key
    return None


class TemplateGenerator(object):
    """
    Abstract base class for building a data template for different data types.
    This is a generic class that is initialized with a path that identifies
    the data to be built.

    Parameters
    ----------
    path : string
        tuple containing path of data is described in dfn files
        (<model>,<package>,<block>,<data name>)
    """
    def __init__(self, path):
        self.path = path

    def _get_data_dimensions(self, model):
        from ..data import mfstructure
        from ..coordinates import modeldimensions

        # get structure info
        sim_struct = mfstructure.MFStructure().sim_struct
        package_struct = sim_struct.get_data_structure(self.path[0:-2])

        # get dimension info
        data_struct = sim_struct.get_data_structure(self.path)
        package_dim = modeldimensions.PackageDimensions([model.dimensions],
                                                        package_struct,
                                                        self.path[0:-1])
        return data_struct, modeldimensions.DataDimensions(package_dim,
                                                           data_struct)

    def build_type_header(self, type, data=None):
        from ..data.mfdata import DataStorageType

        if type == DataStorageType.internal_array:
            if isinstance(self, ArrayTemplateGenerator):
                return {'factor':1.0, 'iprn':1, 'data':data}
            else:
                return None
        elif type == DataStorageType.internal_constant:
            return data
        elif type == DataStorageType.external_file:
            return {'filename':'', 'factor':1.0, 'iprn':1}
        return None


class ArrayTemplateGenerator(TemplateGenerator):
    """
    Class that builds a data template for MFArrays.  This is a generic class
    that is initialized with a path that identifies the data to be built.

    Parameters
    ----------
    path : string
        tuple containing path of data is described in dfn files
        (<model>,<package>,<block>,<data name>)

    Methods
    -------
    empty: (model: MFModel, layered: boolean, data_storage_type_list: boolean,
            default_value: int/float) : variable
        Builds a template for the data you need to specify for a specific data
        type (ie. "hk") in a specific model.  The data type and dimensions
        is determined by "path" during initialization of this class and the
        model is passed in to this method as the "model" parameter.  If the
        data is transient a dictionary containing a single stress period
        will be returned.  If "layered" is set to true, data will be returned
        as a list ndarrays, one for each layer.  data_storage_type_list is a
        list of DataStorageType, one type for each layer.  If "default_value"
        is specified the data template will be populated with that value,
        otherwise each ndarray in the data template will be populated with
        np.empty (0 or 0.0 if the DataStorageType is a constant).
    """
    def __init__(self, path):
        super(ArrayTemplateGenerator, self).__init__(path)

    def empty(self, model=None, layered=False, data_storage_type_list=None,
              default_value=None):
        from ..data import mfdata, mfstructure
        from ..data.mfdata import DataStorageType

        # get the expected dimensions of the data
        data_struct, data_dimensions = self._get_data_dimensions(model)
        datum_type = data_struct.get_datum_type()
        data_type = data_struct.get_datatype()
        # build a temporary data storge object
        data_storage = mfdata.DataStorage(
                model.simulation_data,
                data_dimensions,
                mfdata.DataStorageType.internal_array,
                mfdata.DataStructureType.recarray)
        dimension_list = data_storage.get_data_dimensions(None)

        # if layered data
        if layered and dimension_list[0] > 1:
            data_with_header = ''
            if data_storage_type_list is not None and \
                    len(data_storage_type_list) != dimension_list[0]:
                except_str = 'data_storage_type_list specified with the ' \
                             'wrong size.  Size {} but expected to be ' \
                             'the same as the number of layers, ' \
                             '{}.'.format(len(data_storage_type_list),
                                          dimension_list[0])
                print(except_str)
                raise mfstructure.MFDataException(except_str)
            # build each layer
            data_with_header = []
            for layer in range(0, dimension_list[0]):
                # determine storage type
                if data_storage_type_list is None:
                    data_storage_type = DataStorageType.internal_array
                else:
                    data_storage_type = data_storage_type_list[layer]
                # build data type header
                data_with_header.append(self._build_layer(datum_type,
                                                          data_storage_type,
                                                          default_value,
                                                          dimension_list))
        else:
            if data_storage_type_list is None or \
                    data_storage_type_list[0] == \
                            DataStorageType.internal_array:
                data_storage_type = DataStorageType.internal_array
            else:
                data_storage_type = data_storage_type_list[0]
            # build data type header
            data_with_header = self._build_layer(datum_type,
                                                 data_storage_type,
                                                 default_value,
                                                 dimension_list, True)

        # if transient/multiple list
        if data_type == mfstructure.DataType.array_transient:
            # Return as dictionary
            return {0:data_with_header}
        else:
            return data_with_header

    def _build_layer(self, data_type, data_storage_type, default_value,
                     dimension_list, all_layers=False):
        from ..data.mfdata import DataStorageType

        # build data
        if data_storage_type == DataStorageType.internal_array:
            if default_value is None:
                if all_layers:
                    data = np.empty(dimension_list, data_type)
                else:
                    data = np.empty(dimension_list[1:], data_type)
            else:
                if all_layers:
                    data = np.full(dimension_list, default_value, data_type)
                else:
                    data = np.full(dimension_list[1:], default_value,
                                   data_type)
        elif data_storage_type == DataStorageType.internal_constant:
            if default_value is None:
                if data_type == np.int:
                    data = 0
                else:
                    data = 0.0
            else:
                data = default_value
        else:
            data = None
        # build data type header
        return self.build_type_header(data_storage_type, data)


class ListTemplateGenerator(TemplateGenerator):
    """
    Class that builds a data template for MFLists.  This is a generic class
    that is initialized with a path that identifies the data to be built.

    Parameters
    ----------
    path : string
        tuple containing path of data is described in dfn files
        (<model>,<package>,<block>,<data name>)

    Methods
    -------
    empty: (maxbound: int, aux_vars: list, boundnames: boolean, nseg: int) :
            dictionary
        Builds a template for the data you need to specify for a specific data
        type (ie. "periodrecarray") in a specific model.  The data type is
        determined by "path" during initialization of this class.  If the data
        is transient a dictionary containing a single stress period will be
        returned.  The number of entries in the recarray are determined by
        the "maxbound" parameter.  The "aux_vars" parameter is a list of aux
        var names to be used in this data list.  If boundnames is set to
        true and boundname field will be included in the recarray.  nseg is
        only used on list data that contains segments.  If timeseries is true,
        a template that is compatible with time series data is returned.
    """
    def __init__(self, path):
        super(ListTemplateGenerator, self).__init__(path)

    def _build_template_data(self, type_list):
        template_data = []
        for type in type_list:
            if type[1] == int:
                template_data.append(0)
            elif type[1] == float:
                template_data.append(np.nan)
            else:
                template_data.append(None)
        return tuple(template_data)

    def empty(self, model, maxbound=None, aux_vars=None, boundnames=False,
              nseg=None, timeseries=False, stress_periods=None):
        from ..data import mfdata, mfstructure

        data_struct, data_dimensions = self._get_data_dimensions(model)
        data_type = data_struct.get_datatype()
        # build a temporary data storge object
        data_storage = mfdata.DataStorage(
                model.simulation_data,
                data_dimensions,
                mfdata.DataStorageType.internal_array,
                mfdata.DataStructureType.recarray)

        # build type list
        type_list = data_storage.build_type_list(nseg=nseg)
        if aux_vars is not None:
            if len(aux_vars) > 0 and (isinstance(aux_vars[0], list) or
                    isinstance(aux_vars[0], tuple)):
                aux_vars = aux_vars[0]
            for aux_var in aux_vars:
                type_list.append((aux_var, object))
        if boundnames:
            type_list.append(('boundnames', object))

        if timeseries:
            # fix type list to make all types objects
            for index in range(0, len(type_list)):
                type_list[index] = (type_list[index][0], object)

        # build rec array
        template_data = self._build_template_data(type_list)
        rec_array_data = []
        if maxbound is not None:
            for index in range(0, maxbound):
                rec_array_data.append(template_data)
        else:
            rec_array_data.append(template_data)
        rec_array = np.rec.array(rec_array_data, type_list)

        # if transient/multiple list
        if data_type == mfstructure.DataType.list_transient or \
                data_type == mfstructure.DataType.list_multiple:
            # Return as dictionary
            if stress_periods is None:
                return {0:rec_array}
            else:
                template = {}
                for stress_period in stress_periods:
                    template[stress_period] = deepcopy(rec_array)
                return template
        else:
            return rec_array


class DatumUtil(object):
    @ staticmethod
    def is_int(str):
        try:
            int(str)
            return True
        except TypeError:
            return False
        except ValueError:
            return False

    @ staticmethod
    def is_float(str):
        try:
            float(str)
            return True
        except TypeError:
            return False
        except ValueError:
            return False


class ArrayUtil(object):
    """
    Class contains miscellaneous methods to work with and compare arrays

    Parameters
    ----------
    path : string
        file path to read/write to
    max_error : float
        maximum acceptable error when doing a compare of floating point numbers

    Methods
    -------
    is_empty_list : (current_list : list) : boolean
        determines if an n-dimensional list is empty
    con_convert : (data : string, data_type : type that has conversion
                   operation) : boolean
        returns true if data can be converted into data_type
    multi_dim_list_size : (current_list : list) : boolean
        determines the number of items in a multi-dimensional list
        'current_list'
    first_item : (current_list : list) : variable
        returns the first item in the list 'current_list'
    next_item : (current_list : list) : variable
        returns the next item in the list 'current_list'
    array_comp : (first_array : list, second_array : list) : boolean
        compares two lists, returns true if they are identical (with max_error)
    spilt_data_line : (line : string) : list
        splits a string apart (using split) and then cleans up the results
        dealing with various MODFLOW input file releated delimiters
    clean_numeric : (text : string) : string
        returns a cleaned up version of 'text' with only numeric characters
    save_array_diff : (first_array : list, second_array : list,
                       first_array_name : string, second_array_name : string)
        saves lists 'first_array' and 'second_array' to files first_array_name
        and second_array_name and then saves the difference of the two
        arrays to 'debug_array_diff.txt'
    save_array(filename : string, multi_array : list)
        saves 'multi_array' to the file 'filename'
    """
    def __init__(self, path=None, max_error=0.01):
        self.max_error = max_error
        if path:
            self.path = path
        else:
            self.path = os.getcwd()

    @ staticmethod
    def build_layered_array(dimensions, layer_vals):
        assert len(dimensions) <= 3
        assert dimensions[0] == len(layer_vals)
        dim_tuple = ()
        for dimension in dimensions:
            dim_tuple += (dimension,)
        if type(layer_vals[0]) == float:
            new_array = np.empty(dim_tuple, np.float)
        else:
            new_array = np.empty(dim_tuple, np.int)

        for layer in range(0, len(layer_vals)):
            if len(dimensions) == 3:
                for row in range(0, dimensions[1]):
                    for col in range(0, dimensions[2]):
                        new_array[layer,row,col] = layer_vals[layer]
            elif len(dimensions) == 2:
                for row in range(0, dimensions[1]):
                    new_array[layer,row] = layer_vals[layer]
            else:
                new_array[layer] = layer_vals[layer]
        return new_array

    @ staticmethod
    def has_one_item(current_list):
        if not isinstance(current_list, list) and not isinstance(current_list,
                                                                 np.ndarray):
            return True
        if len(current_list) != 1:
            return False
        if (isinstance(current_list[0], list) or
                isinstance(current_list, np.ndarray)) and \
                len(current_list[0] != 0):
            return False
        return True

    @ staticmethod
    def is_empty_list(current_list):
        if not isinstance(current_list, list):
            return not current_list

        for item in current_list:
            if isinstance(item, list):
                # still in a list of lists, recurse
                if not ArrayUtil.is_empty_list(item):
                    return False
            else:
                return False

        return True

    @ staticmethod
    def can_convert(data, data_type):
        try:
            data_type(data)
            return True
        except TypeError:
            return False
        except ValueError:
            return False

    @ staticmethod
    def max_multi_dim_list_size(current_list):
        max_length = -1
        for item in current_list:
            if len(item) > max_length:
                max_length = len(item)
        return max_length

    @ staticmethod
    def multi_dim_list_size(current_list):
        if current_list is None:
            return 0
        if not isinstance(current_list, list):
            return 1
        item_num = 0
        for item, last_item in ArrayUtil.next_item(current_list):
            item_num += 1
        return item_num

    @ staticmethod
    def first_item(current_list):
        if not isinstance(current_list, list):
            return current_list

        for item in current_list:
            if isinstance(item, list):
                # still in a list of lists, recurse
                return ArrayUtil.first_item(item)
            else:
                return item

    @ staticmethod
    def next_item(current_list, new_list=True, nesting_change=0,
                  end_of_list=True):
        # returns the next item in a nested list along with other information:
        # (<next item>, <end of list>, <entering new list>,
        #  <change in nesting level>
        if not isinstance(current_list, list) and \
                not isinstance(current_list, np.ndarray):
            yield (current_list, end_of_list, new_list, nesting_change)
        else:
            list_size = 1
            for item in current_list:
                if isinstance(item, list) or isinstance(current_list,
                                                        np.ndarray):
                    # still in a list of lists, recurse
                    for item in ArrayUtil.next_item(item, list_size == 1,
                                                    nesting_change + 1,
                                                    list_size ==
                                                    len(current_list)):
                        yield item
                    nesting_change = -(nesting_change + 1)
                else:
                    yield (item, list_size == len(current_list),
                           list_size == 1, nesting_change)
                    nesting_change = 0
                list_size += 1

    def array_comp(self, first_array, second_array):
        diff = first_array - second_array
        max = np.max(np.abs(diff))
        if max > self.max_error:
            return False
        return True

    @staticmethod
    def split_data_line(line, external_file=False):
        quote_list = {"'", '"'}
        delimiter_list = {',': 0, '\t': 0, ' ': 0}
        clean_line = line.strip().split()
        if external_file:
            # try lots of different delimitiers for external files and use the
            # one the breaks the data apart the most
            max_split_size = len(clean_line)
            max_split_type = None
            for delimiter in delimiter_list:
                alt_split = line.strip().split(delimiter)
                if len(alt_split) > max_split_size:
                    max_split_size = len(alt_split)
                    max_split_type = delimiter
            if max_split_type is not None:
                clean_line = line.strip().split(max_split_type)

        arr_fixed_line = []
        index = 0
        # loop through line to fix quotes and delimiters
        while index < len(clean_line):
            item = clean_line[index]
            if item not in delimiter_list:
                if item and item[0] in quote_list:
                    # starts with a quote, handle quoted text
                    if item[-1] in quote_list:
                        arr_fixed_line.append(item[1:-1])
                    else:
                        arr_fixed_line.append(item[1:])
                        # loop until trailing quote found
                        while index < len(clean_line):
                            index += 1
                            if index < len(clean_line):
                                item = clean_line[index]
                                if item[-1] in quote_list:
                                    arr_fixed_line[-1] = \
                                        '{} {}'.format(arr_fixed_line[-1],
                                                       item[:-1])
                                    break
                                else:
                                    arr_fixed_line[-1] = \
                                        '{} {}'.format(arr_fixed_line[-1],
                                                       item)
                else:
                    # no quote, just append
                    arr_fixed_line.append(item)
            index += 1

        return arr_fixed_line

    @staticmethod
    def clean_numeric(text):
        if isinstance(text, str):
            numeric_chars = {'0': 0, '1': 0, '2': 0, '3': 0, '4': 0, '5': 0,
                             '6': 0, '7': 0, '8': 0, '9': 0, '.': 0, '-': 0}
            # remove all non-numeric text from leading and trailing positions
            # of text
            if text:
                while text and (text[0] not in numeric_chars or text[-1]
                                not in numeric_chars):
                    if text[0] not in numeric_chars:
                        text = text[1:]
                    if text and text[-1] not in numeric_chars:
                        text = text[:-1]
        return text

    def save_array_diff(self, first_array, second_array, first_array_name,
                        second_array_name):
        try:
            diff = first_array - second_array
            self.save_array(first_array_name, first_array)
            self.save_array(second_array_name, second_array)
            self.save_array('debug_array_diff.txt', diff)
        except:
            print("An error occurred while outputting array differences.")
            return False
        return True

    # Saves an array with up to three dimensions
    def save_array(self, filename, multi_array):
        file_path = os.path.join(self.path, filename)
        with open(file_path, 'w') as outfile:
            outfile.write('{}\n'.format(str(multi_array.shape)))
            if len(multi_array.shape) == 4:
                for slice in multi_array:
                    for second_slice in slice:
                        for third_slice in second_slice:
                            for item in third_slice:
                                outfile.write(' {:10.3e}'.format(item))
                            outfile.write('\n')
                        outfile.write('\n')
                    outfile.write('\n')
            elif len(multi_array.shape) == 3:
                for slice in multi_array:
                    np.savetxt(outfile, slice, fmt='%10.3e')
                    outfile.write('\n')
            else:
                np.savetxt(outfile, multi_array, fmt='%10.3e')


class ArrayIndexIter(object):
    def __init__(self, array_shape):
        self.array_shape = array_shape
        self.current_location = []
        self.first_item = True
        for item in array_shape:
            self.current_location.append(0)
        self.current_index = len(self.current_location) - 1

    def __iter__(self):
        return self

    def __next__(self):
        if self.first_item:
            self.first_item = False
            if len(self.current_location) > 1:
                return tuple(self.current_location)
            else:
                return self.current_location[0]
        while self.current_index >= 0:
            location = self.current_location[self.current_index]
            if location < self.array_shape[self.current_index] - 1:
                self.current_location[self.current_index] += 1
                self.current_index = len(self.current_location) - 1
                if len(self.current_location) > 1:
                    return tuple(self.current_location)
                else:
                    return self.current_location[0]
            else:
                self.current_location[self.current_index] = 0
                self.current_index -= 1
        raise StopIteration()

    next = __next__  # Python 2 support


class MultiListIter(object):
    def __init__(self, multi_list, detailed_info=False):
        self.multi_list = multi_list
        self.detailed_info = detailed_info
        self.val_iter = ArrayUtil.next_item(self.multi_list)

    def __iter__(self):
        return self

    def __next__(self):
        next_val = next(self.val_iter)
        if self.detailed_info:
            return next_val
        else:
            return next_val[0]

    next = __next__  # Python 2 support


class ConstIter(object):
    def __init__(self, value):
        self.value = value

    def __iter__(self):
        return self

    def __next__(self):
        return self.value

    next = __next__  # Python 2 support


class FileIter(object):
    def __init__(self, file_path):
        self.eof = False
        try:
            self._fd = open(file_path, 'r')
        except:
            self.eof = True
        self._current_data = None
        self._data_index = 0
        self._next_line()

    def __iter__(self):
        return self

    def __next__(self):
        if self.eof:
            raise StopIteration()
        else:
            while self._current_data is not None and \
                  self._data_index >= len(self._current_data):
                self._next_line()
                self._data_index = 0
                if self.eof:
                    raise StopIteration()
            self._data_index += 1
            return self._current_data[self._data_index-1]

    def close(self):
        self._fd.close()

    def _next_line(self):
        if self.eof:
            return
        data_line = self._fd.readline()
        if data_line is None:
            self.eof = True
            return
        self._current_data = ArrayUtil.split_data_line(data_line)

    next = __next__  # Python 2 support


class NameIter(object):
    def __init__(self, name, first_not_numbered=True):
        self.name = name
        self.iter_num = -1
        self.first_not_numbered = first_not_numbered

    def __iter__(self):
        return self

    def __next__(self):
        self.iter_num += 1
        if self.iter_num == 0 and self.first_not_numbered:
            return self.name
        else:
            return '{}_{}'.format(self.name, self.iter_num)

    next = __next__  # Python 2 support


class PathIter(object):
    def __init__(self, path, first_not_numbered=True):
        self.path = path
        self.name_iter = NameIter(path[-1], first_not_numbered)

    def __iter__(self):
        return self

    def __next__(self):
        return self.path[0:-1] + (self.name_iter.__next__(),)

    next = __next__  # Python 2 support


class MFDocString(object):
    """
    Helps build a python class doc string

    Parameters
    ----------
    description : string
        description of the class

    Attributes
    ----------
    indent: string
        indent to use in doc string
    description : string
        description of the class
    parameter_header : string
        header for parameter section of doc string
    parameters : list
        list of docstrings for class parameters

    Methods
    -------
    add_parameter : (param_name : string, param_type : string,
                     param_descr : string)
        adds doc string for a parameter with name 'param_name', type
        'param_type' and description 'param_descr'
    get_doc_string : () : string
        builds and returns the docstring for the class
    """
    def __init__(self, description):
        self.indent = '    '
        self.description = self._resolve_string(description)
        self.parameter_header = '{}Attributes\n{}' \
                                '----------'.format(self.indent, self.indent)
        self.parameters = []

    def add_parameter(self, param_name, param_type, param_descr):
        # add tabs to all new lines in the parameter description
        if param_descr:
            param_descr_array = param_descr.split('\n')
        else:
            param_descr_array = ['\n']
        twr = TextWrapper(width=79, initial_indent=self.indent * 2,
                          subsequent_indent='  {}'.format(self.indent * 2))
        for index in range(0, len(param_descr_array)):
            param_descr_array[index] = '\n'.join(twr.wrap(param_descr_array[
                                                              index]))
        param_descr = '\n'.join(param_descr_array)
        # build doc string
        param_doc_string = '{} : {}'.format(param_name, param_type)
        twr = TextWrapper(width=79, initial_indent='',
                          subsequent_indent='  {}'.format(self.indent))
        param_doc_string = '\n'.join(twr.wrap(param_doc_string))
        new_string = '{}\n{}'.format(param_doc_string, param_descr)
        param_doc_string = self._resolve_string((new_string))
        self.parameters.append(param_doc_string)

    def get_doc_string(self):
        doc_string = '{}"""\n{}{}\n\n{}\n'.format(self.indent, self.indent,
                                                  self.description,
                                                  self.parameter_header)
        for parameter in self.parameters:
            doc_string += '{}{}\n'.format(self.indent, parameter)
        doc_string += '\n{}"""'.format(self.indent)
        return doc_string

    def _resolve_string(self, doc_string):
        doc_string = doc_string.replace('\\texttt{', '')
        doc_string = doc_string.replace('}', '')
        doc_string = doc_string.replace('~\\ref{table:', '')
        doc_string = doc_string.replace('\\reftable:', '')
        return doc_string
