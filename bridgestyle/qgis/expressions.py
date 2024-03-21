try:
    from qgis.core import QgsExpressionNode, QgsExpression, QgsExpressionNodeBinaryOperator
except (ImportError, ModuleNotFoundError):
    QgsExpressionNodeBinaryOperator = None


class UnsupportedExpressionException(Exception):
    """ Exception raised for unsupported expressions. """
    pass


class CompatibilityException(Exception):
    """ Exception raised for compatibility issues. """
    pass


OGC_PROPERTYNAME = "PropertyName"
OGC_IS_EQUAL_TO = "PropertyIsEqualTo"
OGC_IS_NULL = "PropertyIsNull"
OGC_IS_NOT_NULL = "PropertyIsNotNull"
OGC_IS_LIKE = "PropertyIsLike"
OGC_SUB = "Sub"

_qbo = None
binaryOps = {}

if QgsExpressionNodeBinaryOperator is not None:
    if hasattr(QgsExpressionNodeBinaryOperator, "boOr"):
        # QGIS 3.16 may have the operators one level up
        _qbo = QgsExpressionNodeBinaryOperator
    elif hasattr(QgsExpressionNodeBinaryOperator.BinaryOperator, "boOr"):
        _qbo = QgsExpressionNodeBinaryOperator.BinaryOperator

if _qbo is not None:
    binaryOps = {
        _qbo.boOr: "Or",
        _qbo.boAnd: "And",
        _qbo.boEQ: OGC_IS_EQUAL_TO,
        _qbo.boNE: "PropertyIsNotEqualTo",
        _qbo.boLE: "PropertyIsLessThanOrEqualTo",
        _qbo.boGE: "PropertyIsGreaterThanOrEqualTo",
        _qbo.boLT: "PropertyIsLessThan",
        _qbo.boGT: "PropertyIsGreaterThan",
        _qbo.boRegexp: None,
        _qbo.boLike: OGC_IS_LIKE,
        _qbo.boNotLike: None,
        _qbo.boILike: None,
        _qbo.boNotILike: None,
        _qbo.boIs: None,
        _qbo.boIsNot: None,
        _qbo.boPlus: "Add",
        _qbo.boMinus: OGC_SUB,
        _qbo.boMul: "Mul",
        _qbo.boDiv: "Div",
        _qbo.boIntDiv: None,
        _qbo.boMod: None,
        _qbo.boPow: None,
        _qbo.boConcat: None,
    }
else:
    # QGIS version is not compatible
    raise CompatibilityException("QGIS version is not compatible with bridgestyle")


unaryOps = ["Not", OGC_SUB]

# QGIS function names mapped to OGC/WFS2.0 function names
# See https://docs.geoserver.org/stable/en/user/filter/function_reference.html
functions = {
    "radians": "toRadians",
    "degrees": "toDegrees",
    "floor": "floor",
    "ceil": "ceil",
    "area": "area",
    "buffer": "buffer",
    "centroid": "centroid",
    "if": "if_then_else",
    "bounds": "envelope",
    "distance": "distance",
    "convex_hull": "convexHull",
    "end_point": "endPoint",
    "start_point": "startPoint",
    "x": "getX",
    "y": "getY",
    "concat": "Concatenate",
    "substr": "strSubstr",
    "lower": "strToLower",
    "upper": "strToUpper",
    "replace": "strReplace",
    "exterior_ring": "exteriorRing",
    "intersects": "intersects",
    "overlaps": "overlaps",
    "touches": "touches",
    "within": "within",
    "relates": "relates",
    "crosses": "crosses",
    "disjoint": "disjoint",
    "geom_from_wkt": "geomFromWKT",
    "perimeter": "geomLength",
    "union": "union",
    "acos": "acos",
    "asin": "asin",
    "atan": "atan",
    "atan2": "atan2",
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "ln": "log",
    "title": "strCapitalize",
    "translate": "offset",
    "min": "min",
    "max": "max",
    "to_int": "parseLong",
    "to_real": "parseDouble",
    "to_string": "to_string",  # Not mapped to function, but required by MapBox GL
}  # TODO: test/improve


def walkExpression(node, layer, null_allowed=False, cast_to=None):
    exp = None
    cast_to = str(cast_to).lower()
    if node.nodeType() == QgsExpressionNode.ntBinaryOperator:
        exp = handleBinary(node, layer)
    elif node.nodeType() == QgsExpressionNode.ntUnaryOperator:
        exp = handleUnary(node, layer)
    elif node.nodeType() == QgsExpressionNode.ntInOperator:
        exp = handle_in(node, layer)
    elif node.nodeType() == QgsExpressionNode.ntFunction:
        exp = handleFunction(node, layer)
    elif node.nodeType() == QgsExpressionNode.ntLiteral:
        exp = handleLiteral(node)
        if exp is None and null_allowed:
            return exp
        if cast_to == 'string':
            exp = str(exp)
        elif cast_to.startswith('integer'):
            exp = int(exp)
        elif cast_to == 'real':
            exp = float(exp)
    elif node.nodeType() == QgsExpressionNode.ntColumnRef:
        exp = handleColumnRef(node, layer)
    # elif node.nodeType() == QgsExpression.ntCondition:
    #    filt = handle_condition(nod)
    if exp is None:
        raise UnsupportedExpressionException(
            "Unsupported operator in expression: '%s'" % str(node)
        )
    return exp


# handle IN expression
# convert to a series of (A='a') OR (B='b')
def handle_in(node, layer):
    if node.isNotIn():
        raise UnsupportedExpressionException("expression NOT IN is unsupported")
    # convert this expression to another (equivalent Expression)
    if node.node().nodeType() != QgsExpressionNode.ntColumnRef:
        raise UnsupportedExpressionException("expression  IN doesn't ref column!")
    if node.list().count() == 0:
        raise UnsupportedExpressionException(
            "expression  IN doesn't have anything inside the IN"
        )

    colRef = handleColumnRef(node.node(), layer)
    propEqualsExprs = []  # one for each of the literals in the expression
    for item in node.list().list():
        if item.nodeType() != QgsExpressionNode.ntLiteral:
            raise UnsupportedExpressionException("expression IN isn't literal")
        # equals_expr = QgsExpressionNodeBinaryOperator(2,colRef,item) #2 is "="
        equals_expr = [binaryOps[_qbo.boEQ], colRef, handleLiteral(item)]  # 2 is "="
        propEqualsExprs.append(equals_expr)

    # build into single expression
    if len(propEqualsExprs) == 1:
        return propEqualsExprs[0]  # handle 1 item in the list
    accum = [binaryOps[_qbo.boOr], propEqualsExprs[0], propEqualsExprs[1]]  # 0="OR"
    for idx in range(2, len(propEqualsExprs)):
        accum = [binaryOps[_qbo.boOr], accum, propEqualsExprs[idx]]  # 0="OR"
    return accum


def handleBinary(node, layer):
    op = node.op()
    retOp = binaryOps[op]
    left = node.opLeft()
    right = node.opRight()
    retLeft = walkExpression(left, layer)
    castTo = None
    if left.nodeType() == QgsExpressionNode.ntColumnRef:
        fields = [f for f in layer.fields() if f.name() == retLeft[-1]]
        if len(fields) == 1:
            # Field has been found, get its type
            castTo = fields[0].typeName()
    retRight = walkExpression(right, layer, True, castTo)
    if (retOp is retRight is None):
        if op == _qbo.boIs:
            # Special case for IS NULL
            retOp = OGC_IS_NULL
        elif op == _qbo.boIsNot:
            # Special case for IS NOT NULL
            retOp = OGC_IS_NOT_NULL
    return [retOp, retLeft, retRight]


def handleUnary(node, layer):
    op = node.op()
    operand = node.operand()
    retOp = unaryOps[op]
    retOperand = walkExpression(operand, layer)
    if retOp == OGC_SUB:  # handle the particular case of a minus in a negative number
        return [retOp, 0, retOperand]
    else:
        return [retOp, retOperand]


def handleLiteral(node):
    val = node.value()
    if isinstance(val, str):
        val = val.replace("\n", "\\n")
    return val


def handleColumnRef(node, layer):
    if layer is not None:
        attrName = node.name().casefold()
        for field in layer.fields():
            if field.name().casefold() == attrName:
                return [OGC_PROPERTYNAME, field.name()]
    return [OGC_PROPERTYNAME, node.name()]


def handleFunction(node, layer):
    fnIndex = node.fnIndex()
    func = QgsExpression.Functions()[fnIndex].name()
    if func == "$geometry":
        return [OGC_PROPERTYNAME, "geom"]
    fname = functions.get(func)
    if fname is not None:
        elems = [fname]
        args = node.args()
        if args is not None:
            args = args.list()
            for arg in args:
                elems.append(walkExpression(arg, layer))
        return elems
    else:
        raise UnsupportedExpressionException(
            "Unsupported function in expression: '%s'" % func
        )
