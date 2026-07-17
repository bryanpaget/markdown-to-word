-- ascii-to-image.lua
-- Converts ```ascii blocks to high-resolution PNG using ditaa.
-- Options:
--   --scale 2.0          : bigger resolution for sharp text.
--   --no-antialias       : crisp pixel edges.
--   --round-corners      : rounded corners on boxes.
--   --no-shadows         : remove drop shadows.
--   --transparent        : transparent background (optional).

local function run_ditaa(content)
  local tmp = os.tmpname() .. ".txt"
  local f = io.open(tmp, "w")
  if not f then
    io.stderr:write("Failed to create temp text file\n")
    return nil
  end
  f:write(content)
  f:close()

  local outfile = "ascii-diagram-" .. os.time() .. ".png"
  -- Combine options for a cleaner diagram.
  local cmd = string.format(
    "ditaa --scale 2.0 --no-antialias --round-corners --no-shadows --transparent %s %s",
    tmp, outfile
  )
  local ret = os.execute(cmd)
  os.remove(tmp)

  if not ret then
    io.stderr:write("ditaa failed\n")
    return nil
  end

  local img = io.open(outfile, "r")
  if img then
    img:close()
    return outfile
  else
    io.stderr:write("ditaa did not produce output file\n")
    return nil
  end
end

function CodeBlock(el)
  if el.classes:includes("ascii") then
    io.stderr:write("Converting ascii block...\n")
    local img_path = run_ditaa(el.text)
    if img_path then
      -- Display at 90% of text width, preserving sharpness.
      local latex = string.format([[
\begin{center}
\fbox{\includegraphics[width=0.9\textwidth]{%s}}
\end{center}
]], img_path)
      return pandoc.RawBlock('latex', latex)
    else
      io.stderr:write("Fallback: keeping original code block\n")
      return el
    end
  end
end
