BEGIN {
  print "Uso: make [target]"
  print ""
}
{ lines[NR] = $0; n = NR }
END {
  for (i = 1; i <= n; i++) dash[i] = (lines[i] ~ /^# *-+ *$/)
  group = ""
  comment = ""
  comment_at = 0
  lastgroup = ""
  for (i = 1; i <= n; i++) {
    line = lines[i]
    if (line ~ /^#/) {
      if (dash[i]) continue
      # commento tra due linee di decorazione: titolo di gruppo
      if (i > 1 && dash[i-1] && i < n && dash[i+1]) {
        group = line
        sub(/^# +/, "", group)
        comment = ""
        comment_at = 0
        continue
      }
      comment = line
      sub(/^# +/, "", comment)
      comment_at = i
      continue
    }
    if (line ~ /^[A-Za-z0-9_.-]+:/) {
      name = line
      sub(/:.*/, "", name)
      if (name == ".PHONY") continue
      if (group != lastgroup) {
        print ""
        print group
        lastgroup = group
      }
      doc = (comment_at == i - 1) ? comment : ""
      printf "  %-20s %s\n", name, doc
      comment = ""
      comment_at = 0
    }
  }
}
