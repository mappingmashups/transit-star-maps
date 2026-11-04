@background: black;
//@background: transparent;
@starcolor: #ffa;

Map {
  background-color: @background;
}



.lines {
  //line-width:2;
  line-width: 8;
  //line-color:lighten(@starcolor,10%);
  line-color: lightgray;
  line-cap: round;
}


.stations {

  // for the same icon
  second/marker-file: url("star_icon_3307/icon_3307_stroke.svg");
  second/marker-width:55;
  second/marker-fill:@background;
  second/marker-line-width: 45;
  second/marker-allow-overlap:true;

  first/marker-file: url("star_icon_3307/icon_3307.svg"); 
  first/marker-width:55;
  first/marker-fill:@starcolor;
  first/marker-allow-overlap:true;
}
