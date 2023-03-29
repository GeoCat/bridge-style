# For now, this is limited to compound labels using the python, VB or Arcade syntax
from ..geostyler.custom_properties import WellKnownText


def convertExpression(expression, engine, tolowercase):
    if engine == "Arcade":
        expression = convertArcadeExpression(expression)
    if tolowercase:
        expression = expression.lower()
    if "+" in expression or "&" in expression:
        if "+" in expression:
            tokens = expression.split("+")[::-1]
        else:
            tokens = expression.split("&")[::-1]
        addends = []
        for token in tokens:
            if "[" in token:
                addends.append(
                    ["PropertyName", processPropertyName(token)]
                )
            else:
                literal = token.replace('"', "")
                addends.append(replaceSpecialLiteral(literal))
            allOps = addends[0]
            for attr in addends[1:]:
                allOps = ["Concatenate", attr, allOps]
        expression = allOps
    else:
        expression = ["PropertyName", processPropertyName(expression)]
    return expression


def replaceSpecialLiteral(literal):
    if literal == "vbnewline":
        return WellKnownText.NEW_LINE
    return literal


def processPropertyName(token):
    return token.replace("[", "").replace("]", "").strip()


def convertArcadeExpression(expression):
    return expression.replace("$feature.", "")


def stringToParameter(s, tolowercase):
    s = s.strip()
    if "'" in s or '"' in s:
        return s.strip("'\"")
    else:
        if s.isalpha():
            if tolowercase:
                s = s.lower()
            return ["PropertyName", s]
        else:
            return s


# For now, limited to = or IN statements
# There is no formal parsing, just a naive conversion
def convertWhereClause(clause, tolowercase):
    clause = clause.replace("(", "").replace(")", "")
    if " AND " in clause:
        expression = ["And"]
        subexpressions = [s.strip() for s in clause.split(" AND ")]
        expression.extend([convertWhereClause(s, tolowercase)
                          for s in subexpressions])
        return expression
    if "=" in clause:
        tokens = [t.strip() for t in clause.split("=")]
        expression = [
            "PropertyIsEqualTo",
            stringToParameter(tokens[0], tolowercase),
            stringToParameter(tokens[1], tolowercase),
        ]
        return expression
    if "<>" in clause:
        tokens = [t.strip() for t in clause.split("<>")]
        expression = [
            "PropertyIsNotEqualTo",
            stringToParameter(tokens[0], tolowercase),
            stringToParameter(tokens[1], tolowercase),
        ]
        return expression
    if ">" in clause:
        tokens = [t.strip() for t in clause.split(">")]
        expression = [
            "PropertyIsGreaterThan",
            stringToParameter(tokens[0], tolowercase),
            stringToParameter(tokens[1], tolowercase),
        ]
        return expression
    elif " in " in clause.lower():
        clause = clause.replace(" IN ", " in ")
        tokens = clause.split(" in ")
        attribute = tokens[0]
        values = tokens[1].strip("() ").split(",")
        subexpressions = []
        for v in values:
            subexpressions.append(
                [
                    "PropertyIsEqualTo",
                    stringToParameter(attribute, tolowercase),
                    stringToParameter(v, tolowercase),
                ]
            )
        expression = []
        if len(values) == 1:
            return subexpressions[0]
        else:
            accum = ["Or", subexpressions[0], subexpressions[1]]
            for subexpression in subexpressions[2:]:
                accum = ["Or", accum, subexpression]
            return accum

    return clause


def processRotationExpression(expression, rotationType, tolowercase):
    if "$feature" in expression:
        field = convertArcadeExpression(expression)
    else:
        field = processPropertyName(expression)
    propertyNameExpression = ["PropertyName",
                              field.lower() if tolowercase else field]
    if rotationType == "Arithmetic":
        return [
            "Mul",
            propertyNameExpression,
            -1,
        ]
    elif rotationType == "Geographic":
        return [
            "Sub",
            propertyNameExpression,
            90,
        ]
