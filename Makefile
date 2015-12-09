# To install the tilemill project
install:
	mkdir -p ${HOME}/Documents/MapBox/project
	ln -sf "`pwd`" ${HOME}/Documents/MapBox/project/transit-star-maps

bc_skytrain:
	rm -f output.png
	cp -f bc_skytrain.mml project.mml
	../tilemill/index.js export transit-star-maps output.png --format=png --static_zoom=13 --width=3000 --height=3000

bart:
	rm -f output.png
	cp -f bart.mml project.mml
	../tilemill/index.js export transit-star-maps output.png --format=png --static_zoom=13 --width=3000 --height=3000

la_metro:
	rm -f output.png
	cp -f la_metro.mml project.mml
	../tilemill/index.js export transit-star-maps output.png --format=png --static_zoom=13 --width=3000 --height=3000

toronto:
	rm -f output.png
	cp -f toronto.mml project.mml
	../tilemill/index.js export transit-star-maps output.png --format=png --static_zoom=13 --width=3000 --height=3000

trimet:
	rm -f output.png
	cp -f trimet.mml project.mml
	../tilemill/index.js export transit-star-maps output.png --format=png --static_zoom=13 --width=3000 --height=3000
