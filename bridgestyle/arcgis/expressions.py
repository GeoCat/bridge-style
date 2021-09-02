
#For now, this is limited to compound labels using the python or VB syntax
def convertExpression(expression, tolowercase):
    if tolowercase:
        expression = expression.lower()
    if "+" in expression or "&" in expression:
        if "+" in expression:
            tokens = expression.split("+")
        else:
            tokens = expression.split("&")
        addends = []
        for token in tokens:
            if "[" in token:
                addends.append(["PropertyName", token.replace("[", "").replace("]", "").strip()])
            else:
                addends.append(token)


            allOps = addends[0]
            for attr in addends[1:]:
                allOps = ["Concatenate", attr, allOps]
        expression = allOps
    else:
        expression = ["PropertyName", expression.replace("[", "").replace("]", "")]
    return expression
