from typing import Optional, Any

try:
    from qgis.core import (
        QgsExpressionNode, QgsExpression, QgsExpressionNodeBinaryOperator,
        QgsMapLayer, QgsVectorLayer, QgsFeatureRequest, QgsExpressionContext,
        QgsExpressionContextUtils, QgsFields, QgsFeature
    )
except (ImportError, ModuleNotFoundError):
    QgsExpressionNodeBinaryOperator = None
    QgsExpressionNode = None


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
OGC_CONCAT = "Concatenate"
OGC_SUB = "Sub"

_qbo = None      # BinaryOperator
_nt = None       # NodeType
BINOPS_MAP = {}  # Mapping of QGIS binary operators to OGC operators (where possible)

if QgsExpressionNode is None or QgsExpressionNodeBinaryOperator is None:
    raise CompatibilityException("Your QGIS version is not compatible with bridgestyle")

# Make sure that we can find the binary operator types
if hasattr(QgsExpressionNodeBinaryOperator, "boOr"):
    _qbo = QgsExpressionNodeBinaryOperator
elif hasattr(getattr(QgsExpressionNodeBinaryOperator, "BinaryOperator", object()), "boOr"):
    _qbo = QgsExpressionNodeBinaryOperator.BinaryOperator

# Make sure that we can find the node types
if hasattr(QgsExpressionNode, "ntBinaryOperator"):
    _nt = QgsExpressionNode
elif hasattr(getattr(QgsExpressionNode, "NodeType", object()), "ntBinaryOperator"):
    _nt = QgsExpressionNode.NodeType

if _qbo is None or _nt is None:
    raise CompatibilityException("Your QGIS version is not compatible with bridgestyle")

# Mapping of QGIS binary operators to OGC operators (where possible)
BINOPS_MAP = {
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
    _qbo.boPlus: "Add",  # + operator can also be used for concatenation! [#93]
    _qbo.boMinus: OGC_SUB,
    _qbo.boMul: "Mul",
    _qbo.boDiv: "Div",
    _qbo.boIntDiv: None,
    _qbo.boMod: None,
    _qbo.boPow: None,
    _qbo.boConcat: OGC_CONCAT,  # translates || operator
}

# Mapping of QGIS unary operators to OGC operators (where possible)
# Note that this is not a dict but a list, uoMinus is at index 1 and uoNot is at index 0 and there aren't any others
# See https://qgis.org/pyqgis/master/core/QgsExpressionNodeUnaryOperator.html
UNOPS_MAP = ["Not", OGC_SUB]

# QGIS function names mapped to OGC/WFS2.0 function names
# See https://docs.geoserver.org/stable/en/user/filter/function_reference.html
FUNCTION_MAP = {
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
    "concat": OGC_CONCAT,
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


class ExpressionConverter:
    """ Converts QGIS expressions to OGC/WFS2.0 expressions. """

    layer: Optional[QgsMapLayer] = None
    fields: Optional[QgsFields] = None
    context: Optional[QgsExpressionContext] = None
    warnings: set[str] = set()

    def __init__(self, layer: QgsMapLayer):
        """ Initializes a new expression converter instances to work with the given layer.
        If that layer is a vector layer, it will sample the first feature and use it
        for the field list and the expression context. """

        self.layer = layer

        feature = self._get_feature(layer)
        if feature is None:
            # Not a vector layer or no features found
            return

        # Get fields
        self.fields = feature.fields()

        # Set context to the first feature
        try:
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
            context.setFeature(feature)
            self.context = context
        except Exception as e:
            self.warnings.add(f"Can't get expression context for layer '{layer.name()}': {str(e)}")

    def _get_feature(self, layer: QgsMapLayer) -> Optional[QgsFeature]:
        """ Returns the first feature of the given vector layer, or None if there aren't any. """
        if not isinstance(layer, QgsVectorLayer):
            # Can't sample features from non-vector layers
            return None

        try:
            feature = None
            for ft in layer.getFeatures(QgsFeatureRequest().setLimit(10)):
                # Sample 10 features and use the first valid one
                if ft and ft.isValid():
                    feature = ft
                    break
            if not feature:
                raise ValueError("no valid feature found")
        except Exception as e:
            self.warnings.add(f"Can't get sample feature for layer '{layer.name()}': {str(e)}")
            return None

        return feature

    def __del__(self):
        """ Cleans up the expression converter instance. """
        self.layer = None
        self.fields = None
        if isinstance(self.context, QgsExpressionContext):
            self.context.clearCachedValues()
        self.context = None
        self.warnings.clear()

    def convert(self, expression: QgsExpression) -> Any:
        """ Kicks off the recursive expression walker and returns the converted result. """
        if isinstance(expression, QgsExpression):
            if not expression.isValid():
                self.warnings.add(f"Invalid expression: {expression.expression()}")
                return None
            return self._walk(expression.rootNode(), expression)
        self.warnings.add(f"Invalid expression type: {type(expression).__name__}")
        return None

    def _walk(self, node, parent, null_allowed=False, cast_to=None):
        exp = None
        cast_to = str(cast_to).lower()
        if node.nodeType() == _nt.ntBinaryOperator:
            exp = self._handle_binary_op(node, parent)
        elif node.nodeType() == _nt.ntUnaryOperator:
            exp = self._handle_unary_op(node, parent)
        elif node.nodeType() == _nt.ntInOperator:
            exp = self._handle_in_op(node)
        elif node.nodeType() == _nt.ntFunction:
            exp = self._handle_function(node, parent)
        elif node.nodeType() == _nt.ntLiteral:
            exp = self._handle_literal(node)
            if exp is None and null_allowed:
                return exp
            if cast_to == 'string':
                exp = str(exp)
            elif cast_to.startswith('integer'):
                exp = int(exp)
            elif cast_to == 'real':
                exp = float(exp)
        elif node.nodeType() == _nt.ntColumnRef:
            exp = self._handle_column_ref(node)
        if exp is None:
            raise UnsupportedExpressionException(
                "Unsupported operator in expression: '%s'" % str(node)
            )
        return exp

    def _handle_in_op(self, node):
        """
        Handles IN expression. Converts to a series of (A='a') OR (B='b').
        """
        if node.isNotIn():
            raise UnsupportedExpressionException("expression NOT IN is unsupported")
        # convert this expression to another (equivalent Expression)
        if node.node().nodeType() != _nt.ntColumnRef:
            raise UnsupportedExpressionException("expression IN doesn't refer to a column")
        if node.list().count() == 0:
            raise UnsupportedExpressionException("expression IN contains no values")

        colRef = self._handle_column_ref(node.node())
        propEqualsExprs = []  # one for each of the literals in the expression
        for item in node.list().list():
            if item.nodeType() != _nt.ntLiteral:
                raise UnsupportedExpressionException("expression IN isn't literal")
            # equals_expr = QgsExpressionNodeBinaryOperator(2,colRef,item) #2 is "="
            equals_expr = [BINOPS_MAP[_qbo.boEQ], colRef, self._handle_literal(item)]  # 2 is "="
            propEqualsExprs.append(equals_expr)

        # build into single expression
        if len(propEqualsExprs) == 1:
            return propEqualsExprs[0]  # handle 1 item in the list
        accum = [BINOPS_MAP[_qbo.boOr], propEqualsExprs[0], propEqualsExprs[1]]  # 0="OR"
        for idx in range(2, len(propEqualsExprs)):
            accum = [BINOPS_MAP[_qbo.boOr], accum, propEqualsExprs[idx]]  # 0="OR"
        return accum

    def _handle_binary_op(self, node: QgsExpressionNodeBinaryOperator, parent: QgsExpression):
        op = node.op()
        retOp = BINOPS_MAP[op]
        left = node.opLeft()
        right = node.opRight()

        if op == _qbo.boPlus and self.context is not None:
            # Detect special case where ADD (+) is used to concatenate strings [#93]
            result = left.eval(parent, self.context)
            if isinstance(result, str):
                # If the evaluated result is a string, then retOp should become OGC_CONCAT.
                # TODO: because a 3-item list is returned, this may result in multiple nested Concatenate expressions!
                retOp = OGC_CONCAT

        retLeft = self._walk(left, parent)
        castTo = None
        if left.nodeType() == _nt.ntColumnRef:
            fields = [f for f in self.fields if f.name() == retLeft[-1]]
            if len(fields) == 1:
                # Field has been found, get its type
                castTo = fields[0].typeName()
        retRight = self._walk(right, parent, True, castTo)
        if retOp is None and retRight is None:
            if op == _qbo.boIs:
                # Special case for IS NULL
                retOp = OGC_IS_NULL
            elif op == _qbo.boIsNot:
                # Special case for IS NOT NULL
                retOp = OGC_IS_NOT_NULL
        elif retOp is None and isinstance(retRight, bool):
            if op == _qbo.boIs:
                # Special case for IS TRUE/FALSE
                retOp = OGC_IS_EQUAL_TO
            elif op == _qbo.boIsNot:
                # Special case for IS NOT TRUE/FALSE
                retOp = "PropertyIsNotEqualTo"
        return [retOp, retLeft, retRight]

    def _handle_unary_op(self, node, parent):
        op = node.op()
        operand = node.operand()
        retOp = UNOPS_MAP[op]
        retOperand = self._walk(operand, parent)
        if retOp == OGC_SUB:  # handle the particular case of a minus in a negative number
            return [retOp, 0, retOperand]
        else:
            return [retOp, retOperand]

    @staticmethod
    def _handle_literal(node):
        val = node.value()
        if isinstance(val, str):
            val = val.replace("\n", "\\n")
        return val

    def _handle_column_ref(self, node):
        if self.layer is not None:
            attrName = node.name().casefold()
            for field in self.fields:
                if field.name().casefold() == attrName:
                    return [OGC_PROPERTYNAME, field.name()]
        return [OGC_PROPERTYNAME, node.name()]

    def _handle_function(self, node, parent):
        fnIndex = node.fnIndex()
        func = QgsExpression.Functions()[fnIndex].name()
        if func == "$geometry":
            return [OGC_PROPERTYNAME, "geom"]
        fname = FUNCTION_MAP.get(func)
        if fname is not None:
            elems = [fname]
            args = node.args()
            if args is not None:
                args = args.list()
                for arg in args:
                    elems.append(self._walk(arg, parent))
            return elems
        else:
            raise UnsupportedExpressionException(
                f"Unsupported function in expression: '{func}'"
            )
