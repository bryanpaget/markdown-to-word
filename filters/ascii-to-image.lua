-- ascii-to-image.lua
-- Converts ```ascii blocks to PNG via ditaa, outputs both HTML and LaTeX.

local function run_ditaa(content)
  local tmp = os.tmpname() .. ".txt"
  local f = io.open(tmp, "w")
  if not f then return nil end
  f:write(content)
  f:close()

  local outfile = "ascii-diagram-" .. os.time() .. ".png"
  local cmd = string.format("ditaa --scale 2.0 --no-antialias --round-corners --no-shadows %s %s", tmp, outfile)
  os.execute(cmd)
  os.remove(tmp)

  local img = io.open(outfile, "r")
  if img then img:close(); return outfile end
  return nil
end

function CodeBlock(el)
  if el.classes:includes("ascii") then
    local img_path = run_ditaa(el.text)
    if img_path then
      local latex = string.format("\\begin{center}\\fbox{\\includegraphics[width=0.7\\textwidth]{%s}}\\end{center}", img_path)
      local html = string.format('<div style="text-align:center;border:1px solid black;padding:5px;"><img src="%s" style="max-width:80%%;" /></div>', img_path)
      return {
        pandoc.RawBlock('latex', latex),
        pandoc.RawBlock('html', html)
      }
    else
      return el
    end
  end
end
