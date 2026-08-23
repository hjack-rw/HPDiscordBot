from datetime import datetime, timedelta

import itertools

from src.db.engine.common import module_name, DatabaseError


# Data conversions operations
############################################################################################################

# datetime
base_date = datetime(year=2000, month=1, day=1)

def convert_int_to_date(date_in_int:int):
    return base_date + timedelta(days=date_in_int)

def convert_date_to_int(date:datetime):
    date = datetime(year=date.year, month=date.month, day=date.day)
    delta = date - base_date
    return delta.days

# binary
def is_binary(string:str):
    string = set(string)
    if string == {'0', '1'} or string == {'0'} or string == {'1'}:
        return True
    return False

# permutation
class permutation:
    def __init__(self, permutation_in_int:int, requirements:list):
        self.max_idx, self.len_instance = [int(x) for x in requirements[1:]]

   #def convert_int_to_permutation
        self.instance = self.permutations()[permutation_in_int]

    def permutations(self):
        return list(itertools.permutations([x for x in range(self.max_idx)], self.len_instance))

    def check(self):
        test_1 = (type(self.instance) == tuple)
        test_2 = (len(self.instance)  == self.len_instance)
        test_3 = (max(self.instance)   < self.max_idx)
        return test_1 and test_2 and test_3

    def convert_permutation_to_int(self):
        return self.permutations().index(self.instance)

def check_type(key, value, type, spec, required={"is_numeric":False,
                                                 "is_text":   False}):
    """Check the values in question if == type(column)"""

    try:
        if type == "undetermined":
            if not isinstance(value, (int, float)):
                raise DatabaseError(f"'{key}' is neither an int nor a float!")

        elif type == "permutation":
            if not value.check():
                raise DatabaseError(f"'{key}' is not a suited permutation!")

        elif type == "binary":
            if not isinstance(value, str) and not is_binary(value):
                raise DatabaseError(f"'{key}' is not binary!")

        else:
            type_dict = {"int":int,"float":float,"str":str,"datetime":datetime, "bool":bool}

            if not isinstance(value, type_dict[type]):
                raise DatabaseError(f"'{key}' is not a {type}!")

        if spec:
            if type != "binary_object":
                if required["is_numeric"] and spec not in {"less", "lessequal", "great", "greatequal", "inequal"}:
                    raise DatabaseError(f"'{key}' has only numeric filters!")

                if required["is_text"] and spec not in {"below", "belowequal", "upper", "upperequal", "like", "has", "inequal"}:
                    raise DatabaseError(f"'{key}' has only text filters!")
            else:
                raise DatabaseError(f"'{key}' is binary and has no filters!")
    except Exception as error:
        raise DatabaseError(f"{module_name} FILTER error: {str(error)}")

    return True
