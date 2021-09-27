# For now, this is limited to compound labels using the python or VB syntax
def convertExpression(expression, tolowercase):
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
                addends.append(["PropertyName", token.replace("[", "").replace("]", "").strip()])
            else:
                addends.append(token.replace('"', ''))
            allOps = addends[0]
            for attr in addends[1:]:
                allOps = ["Concatenate", attr, allOps]
        expression = allOps
    else:
        expression = ["PropertyName", expression.replace("[", "").replace("]", "")]
    return expression


def stringToParameter(s, tolowercase):
    s = s.strip()
    if "'" in s or '"' in s:
        return s.strip("'\"")
    else:
        s = s.lower() if tolowercase else s
        return ["PropertyName", s]


# For now, limited to = or IN statements
# There is no formal parsing, just a naive conversion
def convertWhereClause(clause, tolowercase):
    if "=" in clause:
        tokens = clause.split("=")
        expression = ["PropertyIsEqualTo",
                      stringToParameter(tokens[0], tolowercase),
                      stringToParameter(tokens[1], tolowercase)]
        return expression
    elif " in " in clause.lower():
        clause = clause.replace(" IN ", " in ")
        tokens = clause.split(" in ")
        attribute = tokens[0]
        values = tokens[1].strip("() ").split(",")
        subexpressions = []
        for v in values:
            subexpressions.append(["PropertyIsEqualTo",
                                  stringToParameter(attribute, tolowercase),
                                  stringToParameter(v, tolowercase)])
        expression = []
        if len(values) == 1:
            return subexpressions[0]
        else:
            accum = ["Or", subexpressions[0], subexpressions[1]]
            for subexpression in subexpressions[2:]:
                accum = ["Or", accum, subexpression]
            return accum

    return clause
