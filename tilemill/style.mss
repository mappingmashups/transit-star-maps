@background: #104;
//@background: transparent;
@starcolor: #ffa;

Map {
  background-color: @background;
}



#barttracks {
  //line-width:2;
  line-width: 8;
  //line-color:lighten(@starcolor,10%);
  line-color: lightgray;
}


#bartstations {

  //second/marker-file: url("star_icon_3307/icon_3307.svg");
  //second/marker-width:12;
  second/marker-width:50;
  second/marker-fill:@background;
  second/marker-line-width: 0;
  //second/marker-line-color:@background;
  second/marker-allow-overlap:true;

  first/marker-file: url("star_icon_3307/icon_3307.svg");
  //first/marker-width:10;  
  first/marker-width:30;  
  first/marker-fill:@starcolor;
  first/marker-allow-overlap:true;


}
