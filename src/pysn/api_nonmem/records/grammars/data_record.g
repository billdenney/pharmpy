// from NONMEM 7.4 spec:
//
// $DATA  [filename|*] [(format)] [IGNORE=c1] [NULL=c2]
//        [IGNORE=(list)...|ACCEPT=(list)...]
//        [NOWIDE|WIDE] [CHECKOUT]
//        [RECORDS=n1|RECORDS=label]
//        [LRECL=n2] [NOREWIND|REWIND]
//        [NOOPEN] [LAST20=n3] [TRANSLATE=(list)]
//        [BLANKOK]
//        [MISDAT=@r@...]

root : ws "*" [ws]
     | ws filename (ws option | ws comment)* [ws]

// dataset (always, unless only ASTERIX terminal)
filename: TEXT | QUOTE

// option rules
?option : "(" [WS] TEXT [WS] ")"                -> format
        | IGNORE [WS] ["="] [WS] (char | _list) -> ignore  // contains 'char' OR 'filter' children
        | ACCEPT [WS] ["="] [WS] _list          -> accept
        | KEY [WS] "=" [WS] VALUE               -> option
        | VALUE                                 -> option

// specific option terminals
char: CHAR | CHARQUOTE
IGNORE : "IGNORE"|"IGNOR"|"IGNO"|"IGN"
ACCEPT : "ACCEPT"|"ACCEP"|"ACCE"|"ACC"

// generic option terminals (key/value)
KEY   : /(?!(IGN|ACC))\w+/      // TODO: use priority (instead of negative lookahead)
VALUE : /(?!(IGN|ACC))[^\s=]+/  // TODO: use priority (instead of negative lookahead)

// _list is only a container (filter thus on accept/ignore)
_list  : "(" filter ("," filter)* ")"
filter : COLUMN operator value        // inlined rules -> terminals (has no depth)
?operator: OP_EQ | OP_STR_EQ | OP_NE | OP_STR_NE | OP_LT | OP_GT | OP_LT_EQ | OP_GT_EQ
?value: TEXT | QUOTE

COLUMN : /\w+/  // TODO: verify correct coverage

// common misc rules
ws      : WS_ALL
comment : ";" [WS] [COMMENT]

// common operators
OP_EQ    : ".EQN."
OP_STR_EQ: ".EQ." | "=" | "=="
OP_NE    : ".NEN."
OP_STR_NE: ".NE." | "="
OP_LT    : ".LT." | "<"
OP_GT    : ".GT." | ">"
OP_LT_EQ : ".LE." | "<="
OP_GT_EQ : ".GE." | ">="

// common misc terminals
WS: (" "|/\t/)+  // inline
WS_ALL: /\s+/    // multiline
DIGIT: "0".."9"
INT: DIGIT+

// common naked/enquoted text terminals
TEXT : /[^"'][^,;()=\s]*/
CHAR : /[^"',;()=\s]/
QUOTE : /("[^"]*")/
      | /('[^']*')/
CHARQUOTE : /("[^"]")/
          | /('[^']')/
COMMENT : /\S.*(?<!\s)/  // no left/right whitespace padding